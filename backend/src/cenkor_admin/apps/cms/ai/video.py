"""AI 视频：正文 → 镜头提示 → 提交任务 → 后台轮询 → 落云存储 → 抽帧封面。

## 为什么这套代码比配图长三倍

配图是「一次 HTTP 一次结果」，视频不是：

1. **提交与产物分离**：POST 只拿到 task_id，产物要再查一次。
2. **分钟级**：60~300 秒。nginx `proxy_read_timeout 60s`，同步等必然 504。
3. **产物 URL 会失效**：通常 24 小时。存 URL 等于存了一个明天就打不开的引用。
4. **产物是二进制大文件**：10~50MB，不能 `resp.content` 全量读内存。
5. **不能当分享卡片**：og:image 只认图片，必须抽首帧。

所以整条链路的骨架是「提交 → 落 job 表 → 后台协程轮询 → 终态时物化」。

## 谁来推进轮询

两条路互为兜底，缺一个都会出问题：

- **后台协程**：提交后立刻 spawn，没人看页面也能跑完。缺点是进程重启就丢。
- **前端查询时顺手推进**（`refresh`）：用户刷新就恢复。缺点是没人看就不动。

只做后台 → 重启后任务永远卡在 running；只做前端 → 用户关掉页面
服务商那边跑完了也没人收，产物 URL 过期，钱白花。

## 两种模式怎么统一

`mode="t2v"` 纯文生视频；`mode="i2v"` 拿已有配图当首帧。服务商侧是同一个
端点、同一套参数，差别只在 content 里多一个 image_url 块。所以业务层
只多一个 `source_media_id` 字段，其余完全共用。
"""

from __future__ import annotations

import asyncio
import io
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _draft_to_text, _record
from cenkor_admin.apps.cms.ai.illustration import _escape, public_media_url
from cenkor_admin.apps.cms.ai.models import CmsAiVideoJob
from cenkor_admin.apps.cms.models import Entry, Media
from cenkor_admin.core.db import AsyncSessionLocal
from cenkor_admin.core.llm import LLMError, VideoTask, get_llm, get_llm_for
from cenkor_admin.core.storage import s3

# 画幅。视频和配图分开定义：配图那套是像素尺寸，视频要的是比例，
# 服务商按比例出片（同比例下分辨率由 resolution 参数决定）。
RATIOS: dict[str, dict[str, str]] = {
    "16:9": {"label": "横屏 16:9", "hint": "官网头图、B 站、YouTube"},
    "9:16": {"label": "竖屏 9:16", "hint": "抖音、视频号、小红书"},
    "1:1": {"label": "方图 1:1", "hint": "信息流、朋友圈"},
}

DURATIONS = (5, 10)
MODES = {
    "t2v": "文生视频",
    "i2v": "图生视频",
}

# 单任务硬超时。服务商最长一般 5 分钟出片，留 3 倍余量：
# 超时后标记失败比让任务永远卡在 running 更诚实 —— 卡着看不出问题在哪。
_JOB_TIMEOUT = 1800
_POLL_FAST = 5  # 前 60 秒 5 秒一次：多数任务在这个区间内完成
_POLL_SLOW = 10
_FAST_WINDOW = 60

# ffmpeg 抽帧吃满一个核。6 核机器放开了跑会拖死后端接口，
# 所以同时最多两个，其余排队。
_FFMPEG_SEM = asyncio.Semaphore(2)

_VIDEO_SYSTEM = """你是工业 B2B 站点的短视频导演。请把给定文章改写成一条 5~10 秒的镜头描述。

要求：
1. 只描述**一个连续镜头**：主体、动作、环境、光线、镜头运动（推/拉/摇/移）
2. 画面里**不要出现任何文字、字幕、数字、水印**（生成模型画中文必糊）
3. 不要人脸特写、不要品牌商标
4. 动作要克制：工业题材适合缓慢运镜、机械运转、光流动，不适合快切和炫技
5. 60~120 字，具体到能拍出来

只输出镜头描述本身，不要 JSON、不要解释、不要标题。
"""


# ---------------------------------------------------------------- 提示词


async def _make_prompt(db: AsyncSession, entry: Entry, hint: str) -> str:
    """正文 → 一条镜头描述。

    只做一次 chat 调用：视频提示词不需要像配图那样额外产出 alt
    （封面的 alt 从标题取就够），少一次调用就少一份成本和等待。
    """
    body = _draft_to_text(entry.title or "", entry.content or {})[:1500]
    user = (
        f"文章标题：{entry.title or '（无标题）'}\n\n"
        f"正文节选：\n{body or '（正文为空）'}\n\n"
        f"{('额外要求：' + hint) if hint else ''}"
    )
    client = get_llm()
    system = await prompts.get(db, "video", _VIDEO_SYSTEM)
    # max_tokens 给到 1600：当前 chat 能力是推理模型（MiniMax-M3.1-Flash），
    # 它会先写 2000+ 字符的思考再给正文，600 的预算会被思考过程吃光，
    # 报「输出被 max_tokens 截断」。镜头描述本身只要 120 字，剩下的都是思考余量。
    res = await client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7,
        max_tokens=1600,
    )
    await _record(
        db,
        kind="video_prompt",
        target=f"entry:{entry.id}",
        result=res,
        params={"stage": "prompt"},
        created_by=None,
        prompt=_VIDEO_SYSTEM,
    )
    text = (res.text or "").strip()
    if not text:
        # 模型没回内容时用标题兜底：宁可镜头平庸，也不要因为一句空话卡住整条链路
        text = f"{entry.title or '工业场景'}，缓慢推镜，自然光，干净构图"
    return text[:800]


# ---------------------------------------------------------------- 提交


def _model_for_mode(mode: str) -> str | None:
    """按模式取模型覆盖值。

    多数服务商把文生和图生拆成两个模型 id，而能力表一行只能绑一个。
    所以允许在能力参数里写 t2v_model / i2v_model，取不到就返回 None，
    让 LLMClient 用它自己被绑定的那个模型。
    """
    try:
        from cenkor_admin.apps.cms.ai.registry import get_endpoint

        ep = get_endpoint("video")
        params = dict(getattr(ep, "params", None) or {}) if ep else {}
    except Exception:
        return None
    key = "i2v_model" if mode == "i2v" else "t2v_model"
    value = str(params.get(key) or "").strip()
    return value or None


async def submit(
    db: AsyncSession,
    entry: Entry,
    *,
    mode: str = "t2v",
    source_media_id: int | None = None,
    ratio: str = "16:9",
    duration: int = 5,
    hint: str = "",
    prompt: str = "",
    created_by: int | None = None,
) -> CmsAiVideoJob:
    """提交一个视频任务，立刻返回 job（不阻塞等产物）。"""
    if mode not in MODES:
        raise ValueError(f"mode 非法：{mode}")
    if ratio not in RATIOS:
        ratio = "16:9"
    duration = 5 if int(duration) not in DURATIONS else int(duration)

    source: Media | None = None
    if mode == "i2v":
        if not source_media_id:
            raise ValueError("图生视频需要指定首帧图片")
        source = await db.get(Media, int(source_media_id))
        if not source or source.deleted_at:
            raise ValueError("首帧图片不存在")
        if not (source.mime or "").startswith("image/"):
            raise ValueError("首帧必须是图片")

    final_prompt = (prompt or "").strip() or await _make_prompt(db, entry, hint)

    client = get_llm_for("video")
    # 文生与图生在多数服务商是两个模型 id（-t2v / -i2v），但能力表只能绑一个。
    # 所以允许在能力参数里用 t2v_model / i2v_model 分别覆盖，不填就用绑定的那个。
    model_override = _model_for_mode(mode)
    # 首帧优先用 CDN 原地址：服务商要能直接拉到，走内网地址它拉不到
    image_url = (source.url or "") if source else None
    task = await client.create_video_task(
        final_prompt,
        image=image_url,
        model=model_override,
        ratio=ratio,
        duration=duration,
        watermark=False,
    )

    job = CmsAiVideoJob(
        site_id=entry.site_id or 1,
        entry_id=entry.id,
        mode=mode,
        status=task.status,
        provider_task_id=task.task_id,
        model=task.model or client.chat_model,
        prompt=final_prompt,
        params={"ratio": ratio, "duration": duration, "mode": mode},
        source_media_id=source.id if source else None,
        created_by=created_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 后台推进：不 await，也不能 await —— await 就是同步等 5 分钟
    asyncio.create_task(_poll_loop(job.id))

    logger.info(
        "cms.video.submitted job={} mode={} task={} ratio={} duration={}",
        job.id,
        mode,
        task.task_id,
        ratio,
        duration,
    )
    return job


# ---------------------------------------------------------------- 轮询


async def _poll_loop(job_id: int) -> None:
    """后台轮询直到终态。独立 session —— 请求的 session 早关了。"""
    started = asyncio.get_event_loop().time()
    try:
        client = get_llm_for("video")
        while True:
            elapsed = asyncio.get_event_loop().time() - started
            if elapsed > _JOB_TIMEOUT:
                await _fail(job_id, f"任务超时（{_JOB_TIMEOUT} 秒仍未出片）")
                return

            async with AsyncSessionLocal() as db:
                job = await db.get(CmsAiVideoJob, job_id)
                if not job or job.status in VideoTask.TERMINAL:
                    return
                task_id = job.provider_task_id
            if not task_id:
                await _fail(job_id, "任务没有服务商编号，无法轮询")
                return

            try:
                task = await client.query_video_task(task_id)
            except LLMError as exc:
                # 轮询失败不等于任务失败：服务商那边可能还在跑，
                # 记一次日志继续下一轮，整体超时会兜住真卡死的情况
                logger.warning("cms.video.poll_failed job={} err={}", job_id, str(exc)[:200])
            else:
                if task.status == "succeeded" and task.video_url:
                    await _materialize(job_id, task)
                    return
                if task.status == "failed":
                    await _fail(job_id, task.error or "服务商返回失败")
                    return
                if task.status == "canceled":
                    await _finish(job_id, "canceled")
                    return
                await _set_status(job_id, task.status)

            await asyncio.sleep(_POLL_FAST if elapsed < _FAST_WINDOW else _POLL_SLOW)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("cms.video.poll_crashed job={}", job_id)
        await _fail(job_id, f"轮询异常：{type(exc).__name__} {str(exc)[:200]}")


async def _set_status(job_id: int, status: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiVideoJob, job_id)
        if job and job.status != status and job.status not in VideoTask.TERMINAL:
            job.status = status
            await db.commit()


async def _fail(job_id: int, error: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiVideoJob, job_id)
        if not job:
            return
        job.status = "failed"
        job.error = error[:2000]
        job.finished_at = datetime.now(UTC)
        await db.commit()
    logger.warning("cms.video.failed job={} err={}", job_id, error[:300])


async def _finish(job_id: int, status: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiVideoJob, job_id)
        if not job:
            return
        job.status = status
        job.finished_at = datetime.now(UTC)
        await db.commit()


# ---------------------------------------------------------------- 物化


def _ext_of_video(data_path: Path) -> tuple[str, str]:
    """按文件头判断容器格式，返回 (扩展名, mime)。"""
    with data_path.open("rb") as f:
        head = f.read(16)
    if head[4:8] == b"ftyp":
        return "mp4", "video/mp4"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm", "video/webm"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBM":
        return "webm", "video/webm"
    return "mp4", "video/mp4"


def _probe_video(path: Path) -> tuple[int | None, int | None, float | None]:
    """读宽高和时长。ffprobe 不可用时返回空，不影响主流程。"""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "default=noprint_wrappers=1", str(path),
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    if out.returncode != 0:
        return None, None, None
    data: dict[str, str] = {}
    for line in out.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    try:
        w = int(data["width"]) if "width" in data else None
        h = int(data["height"]) if "height" in data else None
    except ValueError:
        w = h = None
    try:
        dur = float(data["duration"]) if "duration" in data else None
    except ValueError:
        dur = None
    return w, h, dur


async def _extract_cover(video: Path, out: Path) -> bool:
    """抽首帧当封面。

    从 0.3 秒取而不是第 0 帧：不少片子开头是淡入黑场，抽第 0 帧
    会得到一张纯黑图，分享卡片就是一块黑。
    """
    async with _FFMPEG_SEM:
        def _run() -> bool:
            try:
                proc = subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", "0.3", "-i", str(video),
                        "-frames:v", "1", "-q:v", "3", str(out),
                    ],
                    capture_output=True, timeout=120, check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return False
            return proc.returncode == 0 and out.is_file() and out.stat().st_size > 0

        return await asyncio.to_thread(_run)


async def _upload(
    path: Path,
    mime: str,
    *,
    ext: str,
    alt: str,
    site_id: int,
    created_by: int | None,
    width: int | None = None,
    height: int | None = None,
) -> Media:
    """把本地文件传到云存储并落 cms_media。"""
    bucket = await s3.public_bucket()
    await s3.ensure_bucket(bucket)
    key = f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}"
    data = path.read_bytes()
    await s3.upload_fileobj(bucket, key, io.BytesIO(data), mime)
    try:
        url = await s3.public_url(bucket, key)
    except Exception:
        url = f"/{bucket}/{key}"

    async with AsyncSessionLocal() as db:
        media = Media(
            site_id=site_id,
            bucket=bucket,
            key=key,
            url=url,
            mime=mime,
            size=len(data),
            width=width,
            height=height,
            alt=alt[:200],
            uploader_id=created_by,
        )
        db.add(media)
        await db.commit()
        await db.refresh(media)
    return media


async def _materialize(job_id: int, task: VideoTask) -> None:
    """产物落库：下载 → 上传 → 抽封面 → 更新 job → 记账。"""
    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiVideoJob, job_id)
        if not job:
            return
        entry = await db.get(Entry, job.entry_id) if job.entry_id else None
        prompt = job.prompt
        mode = job.mode
        params = dict(job.params or {})
        site_id = job.site_id
        created_by = job.created_by
        entry_id = job.entry_id
        model = job.model
        task_id = job.provider_task_id

    alt = (entry.title if entry else "AI 生成视频") or "AI 生成视频"

    with tempfile.TemporaryDirectory(prefix="cenkor-video-") as tmp:
        tmpdir = Path(tmp)
        raw = tmpdir / "raw.bin"
        try:
            client = get_llm_for("video")
            await client.download_to_file(task.video_url, raw)
        except Exception as exc:
            await _fail(job_id, f"产物下载失败：{type(exc).__name__} {str(exc)[:300]}")
            return

        ext, mime = _ext_of_video(raw)
        video_path = tmpdir / f"video.{ext}"
        raw.rename(video_path)
        width, height, dur = _probe_video(video_path)

        try:
            media = await _upload(
                video_path,
                mime,
                ext=ext,
                alt=alt,
                site_id=site_id,
                created_by=created_by,
                width=width,
                height=height,
            )
        except Exception as exc:
            await _fail(job_id, f"视频上传失败：{type(exc).__name__} {str(exc)[:300]}")
            return

        cover_id: int | None = None
        cover_path = tmpdir / "cover.jpg"
        if await _extract_cover(video_path, cover_path):
            try:
                cover = await _upload(
                    cover_path,
                    "image/jpeg",
                    ext="jpg",
                    alt=f"{alt}（视频封面）",
                    site_id=site_id,
                    created_by=created_by,
                )
                cover_id = cover.id
            except Exception as exc:
                logger.warning("cms.video.cover_upload_failed job={} err={}", job_id, str(exc)[:200])

    async with AsyncSessionLocal() as db:
        job = await db.get(CmsAiVideoJob, job_id)
        if not job:
            return
        job.status = "succeeded"
        job.media_id = media.id
        job.cover_media_id = cover_id
        job.upstream_url = (task.video_url or "")[:2000]
        job.params = {**(job.params or {}), "width": width, "height": height, "seconds": dur}
        job.finished_at = datetime.now(UTC)
        await db.commit()

        await _record(
            db,
            kind="video",
            target=f"entry:{entry_id}" if entry_id else f"job:{job_id}",
            result=None,
            params={
                **params,
                "model": model,
                "bytes": media.size,
                "cover": bool(cover_id),
                "mode": mode,
                "task": task_id,
            },
            created_by=created_by,
            prompt=prompt,
            model=model,
            latency_ms=int((job.finished_at - job.created_at).total_seconds() * 1000)
            if job.created_at
            else 0,
        )
        # `_record` 内部只 flush 不 commit（便于和业务写同一个事务）。
        # 这里必须显式提交：后台协程没有请求级事务包装，session 一关就回滚，
        # 结果是视频生成成功但成本台账里查不到这条 —— 账会越算越少。
        await db.commit()

    logger.info(
        "cms.video.succeeded job={} media={} cover={} bytes={}",
        job_id,
        media.id,
        cover_id,
        media.size,
    )


# ---------------------------------------------------------------- 查询


async def refresh(db: AsyncSession, job: CmsAiVideoJob) -> CmsAiVideoJob:
    """前端查询时顺手推进一次状态。

    后台协程是主路径，但这个兜底很关键：进程重启后后台协程全丢，
    任务会永远停在 running。用户一刷页面就能把状态追回来。
    """
    if job.status in VideoTask.TERMINAL or not job.provider_task_id:
        return job
    try:
        client = get_llm_for("video")
        task = await client.query_video_task(job.provider_task_id)
    except LLMError as exc:
        logger.warning("cms.video.refresh_failed job={} err={}", job.id, str(exc)[:200])
        return job

    if task.status == "succeeded" and task.video_url:
        # 物化要下载+转存，不能在请求里做（会拖住接口几十秒）。
        # 重开一个后台协程，前端下一次轮询就能看到结果。
        asyncio.create_task(_materialize(job.id, task))
        job.status = "running"
        await db.commit()
        return job
    if task.status == "failed":
        job.status = "failed"
        job.error = (task.error or "服务商返回失败")[:2000]
        job.finished_at = datetime.now(UTC)
        await db.commit()
        return job
    if task.status != job.status:
        job.status = task.status
        await db.commit()
    return job


async def job_to_dict(db: AsyncSession, job: CmsAiVideoJob) -> dict[str, Any]:
    """给前端的形态。视频和封面都给可访问地址，前端不用再拼。"""
    media = await db.get(Media, job.media_id) if job.media_id else None
    cover = await db.get(Media, job.cover_media_id) if job.cover_media_id else None
    params = job.params or {}
    return {
        "id": job.id,
        "entry_id": job.entry_id,
        "mode": job.mode,
        "mode_label": MODES.get(job.mode, job.mode),
        "status": job.status,
        "model": job.model,
        "prompt": job.prompt,
        "params": params,
        "duration": params.get("duration"),
        "ratio": params.get("ratio"),
        "error": job.error,
        "media_id": job.media_id,
        "url": public_media_url(media) if media else None,
        "mime": media.mime if media else None,
        "size": media.size if media else None,
        "width": (media.width or params.get("width")) if media else params.get("width"),
        "height": (media.height or params.get("height")) if media else params.get("height"),
        "cover_url": public_media_url(cover) if cover else None,
        # 分享卡片必须用封面图：og:image 只认图片
        "og_image": public_media_url(cover) if cover else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


# ---------------------------------------------------------------- 应用


async def attach_video(
    db: AsyncSession, entry: Entry, job: CmsAiVideoJob, *, mode: str = "body_head"
) -> str:
    """把已完成的视频挂到条目上。

    - `og_image`：用**封面帧**而不是视频。社交平台抓到 mp4 只会显示空卡片。
    - `body_head`：插 `<video>`，带 `poster`（封面）和 `preload="metadata"` ——
      没有 poster 时列表里是黑块，不带 preload 会把整条视频先拖下来。
    """
    if job.status != "succeeded" or not job.media_id:
        raise ValueError("视频还没生成完成")
    media = await db.get(Media, job.media_id)
    if not media:
        raise ValueError("视频文件不存在")
    cover = await db.get(Media, job.cover_media_id) if job.cover_media_id else None

    if mode == "og_image":
        if not cover:
            raise ValueError("这条视频没有封面帧，无法用作分享图")
        seo = dict(entry.seo or {})
        seo["og_image"] = public_media_url(cover)
        entry.seo = seo
    elif mode == "body_head":
        content = dict(entry.content or {})
        html = content.get("text") or ""
        src = public_media_url(media)
        if src in html:
            return "body_head"
        poster = f' poster="{_escape(public_media_url(cover))}"' if cover else ""
        block = (
            f'<p><video src="{_escape(src)}"{poster} controls preload="metadata" '
            'style="max-width:100%;height:auto"></video></p>'
        )
        content["text"] = f"{block}\n{html}"
        entry.content = content
    elif mode == "none":
        return "none"
    else:
        raise ValueError(f"mode 非法：{mode}")

    entry.updated_at = datetime.now(UTC)
    await db.commit()
    return mode


async def list_jobs(
    db: AsyncSession, *, entry_id: int | None = None, limit: int = 10
) -> list[CmsAiVideoJob]:
    stmt = select(CmsAiVideoJob).order_by(CmsAiVideoJob.id.desc()).limit(max(1, min(limit, 50)))
    if entry_id:
        stmt = stmt.where(CmsAiVideoJob.entry_id == entry_id)
    return list((await db.execute(stmt)).scalars().all())


def options_meta() -> dict[str, Any]:
    return {
        "ratios": [{"key": k, **v} for k, v in RATIOS.items()],
        "durations": list(DURATIONS),
        "modes": [{"key": k, "label": v} for k, v in MODES.items()],
    }
