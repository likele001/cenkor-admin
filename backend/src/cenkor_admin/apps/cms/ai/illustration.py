"""AI 配图：按正文语义生成封面/插图，直接落媒体库。

## 为什么不是「输入一句话生成一张图」

那是个通用文生图工具，不缺我们这一家。这里做的是**配图**：
输入是条目（标题 + 正文），输出是「能放这篇文章头图位置、并且 alt 写对了」的图。

差别在于三件事：
1. **提示词从正文提炼**（不是让用户重新描述一遍文章）
2. **落库到媒体库**（不是给个临时 URL 让用户自己右键另存）
3. **顺手把 alt / og_image 填上**（配图的价值一半在可访问性与分享卡片）

## 为什么先出图再决定怎么用

生图是唯一按「张」计价的能力，贵且慢（十几秒）。所以默认 `apply="none"`：
先给运营看，满意了再用 `POST /ai/media/{id}/attach` 挂上去。
一次生成、两次决策，比「生成即插入、不满意再删」省一半成本。
"""

from __future__ import annotations

import base64
import binascii
import io
import ipaddress
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _draft_to_text, _record
from cenkor_admin.apps.cms.models import Entry, Media
from cenkor_admin.core.llm import LLMError, get_llm, get_llm_for
from cenkor_admin.core.storage import s3

# 尺寸与语义的对应关系。给运营选，但只给三种 —— 头图位的比例是设计定死的，
# 摆一排「1024x1536 / 1536x1024 / 896x1152」只会让人纠结
ASPECTS: dict[str, dict[str, str]] = {
    "wide": {"size": "1280x720", "label": "横图 16:9", "hint": "文章头图 / OG 分享卡片"},
    "square": {"size": "1024x1024", "label": "方图 1:1", "hint": "列表缩略图 / 社媒配图"},
    "portrait": {"size": "720x1280", "label": "竖图 9:16", "hint": "小红书 / 手机端"},
}

STYLES = {
    "photo": "写实摄影风格，自然光线，真实材质质感，不要文字",
    "render": "三维渲染风格，干净的工业质感，柔和景深，不要文字",
    "flat": "扁平化插画风格，有限配色，几何构图，不要文字",
}

APPLY_MODES = ("none", "og_image", "body_head")

_ILLUSTRATION_SYSTEM = """你是工业 B2B 站点的视觉编辑。请为给定文章生成一条**文生图提示词**。

要求：
1. 提示词要能让模型画出「配得上这篇文章」的图：主体具体、场景明确、光线与色调可控
2. 画面中**不要出现任何文字、字母、数字、水印**（生图模型画中文必糊）
3. 不要画人脸特写、不要出现品牌商标
4. 同时给一句 alt 文本（30 字内，描述画面内容，供无障碍与 SEO 使用）

只输出 JSON：{"prompt": "...", "alt": "..."}
"""


def _image_size(data: bytes | None, fallback: str) -> tuple[int | None, int | None]:
    """从 PNG / JPEG 头里读宽高，读不出就用请求尺寸兜底。

    不引入 Pillow：只为两个整数装一个图像库，会把镜像撑大几十 MB。
    """
    if data:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            w = int.from_bytes(data[16:20], "big")
            h = int.from_bytes(data[20:24], "big")
            return w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            n = len(data)
            while i + 9 < n:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
                # SOF0..SOF3 / SOF5..SOF7 / SOF9..SOF11：都含尺寸
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                    h = int.from_bytes(data[i + 5 : i + 7], "big")
                    w = int.from_bytes(data[i + 7 : i + 9], "big")
                    return w, h
                i += 2 + seg_len
    try:
        w_s, h_s = fallback.lower().split("x")
        return int(w_s), int(h_s)
    except Exception:
        return None, None


async def _download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _ext_of(data: bytes, mime: str) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png" if "png" in (mime or "") else "jpg"


async def _resolve_bytes(urls: list[str], b64: list[str]) -> tuple[bytes, str]:
    """服务商两种返回习惯：给 URL 或给 b64。两个都接，先 URL 后 b64。"""
    if urls:
        for u in urls:
            try:
                data = await _download(u)
                if data:
                    return data, u
            except Exception as exc:
                logger.warning("cms.illustration.download_failed url={} err={}", u[:120], exc)
    if b64:
        try:
            return base64.b64decode(b64[0]), ""
        except (binascii.Error, ValueError) as exc:
            raise LLMError(f"图片 base64 解码失败：{exc}") from exc
    raise LLMError("生图结果里既没有可用 URL 也没有 b64_json")


async def _make_prompt(db: AsyncSession, entry: Entry, hint: str, style: str) -> tuple[str, str]:
    """让模型把正文压成一条画面描述 + alt 文本。"""
    import json as _json

    body = _draft_to_text(entry.title or "", entry.content or {})[:1500]
    style_text = STYLES.get(style, STYLES["photo"])
    user = (
        f"文章标题：{entry.title or '（无标题）'}\n\n"
        f"正文节选：\n{body or '（正文为空）'}\n\n"
        f"{('额外要求：' + hint) if hint else ''}\n"
        f"画面风格：{style_text}"
    )

    client = get_llm()
    system = await prompts.get(db, "illustration", _ILLUSTRATION_SYSTEM)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    res = await client.chat(messages, temperature=0.6, max_tokens=1200)
    await _record(
        db,
        kind="illustration_prompt",
        target=f"entry:{entry.id}",
        result=res,
        params={"style": style},
        created_by=None,
        prompt=_ILLUSTRATION_SYSTEM,
    )

    raw = (res.text or "").strip()
    prompt, alt = "", ""
    try:
        match = re.search(r"\{.*\}", raw, re.S)
        obj = _json.loads(match.group(0)) if match else {}
        prompt = str(obj.get("prompt") or "").strip()
        alt = str(obj.get("alt") or "").strip()
    except (ValueError, AttributeError):
        pass
    if not prompt:
        # 模型没按 JSON 回：整段当提示词，alt 用标题兜底。宁可糙也不要断
        prompt = raw[:600] or f"{entry.title or ''} 概念示意图"
    if not alt:
        alt = (entry.title or "配图")[:60]
    return prompt[:800], alt[:120]


async def generate_for_entry(
    db: AsyncSession,
    entry: Entry,
    *,
    hint: str = "",
    style: str = "photo",
    aspect: str = "wide",
    apply: str = "none",
    created_by: int | None = None,
) -> dict[str, Any]:
    """正文 → 图 prompt → 生图 → 落媒体库（可控地应用到条目）。"""
    if apply not in APPLY_MODES:
        raise ValueError(f"apply 非法：{apply}")
    if aspect not in ASPECTS:
        raise ValueError(f"aspect 非法：{aspect}")
    if style not in STYLES:
        style = "photo"

    size = ASPECTS[aspect]["size"]
    prompt, alt = await _make_prompt(db, entry, hint, style)

    # 风格词拼在最后：模型对结尾的指令更敏感，「不要文字」放队尾命中率更高
    full_prompt = f"{prompt}。{STYLES[style]}，主体清晰，构图简洁"

    client = get_llm_for("image")
    result = await client.generate_image(full_prompt, size=size, n=1, response_format="url")
    if result.empty:
        raise LLMError("生图结果为空")

    data, src_url = await _resolve_bytes(result.urls, result.b64)
    mime = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    ext = _ext_of(data, mime)

    bucket = await s3.public_bucket()
    await s3.ensure_bucket(bucket)
    key = f"{datetime.now().strftime('%Y/%m')}/{uuid.uuid4().hex}.{ext}"
    await s3.upload_fileobj(bucket, key, io.BytesIO(data), mime)
    try:
        url = await s3.public_url(bucket, key)
    except Exception:
        url = f"/{bucket}/{key}"

    width, height = _image_size(data, size)
    media = Media(
        site_id=entry.site_id or 1,
        bucket=bucket,
        key=key,
        url=url,
        mime=mime,
        size=len(data),
        width=width,
        height=height,
        alt=alt,
        uploader_id=created_by,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)

    await _record(
        db,
        kind="illustration",
        target=f"entry:{entry.id}",
        result=None,
        params={
            "model": result.model,
            "size": size,
            "style": style,
            "bytes": len(data),
            "upstream": src_url[:200],
        },
        created_by=created_by,
        prompt=full_prompt,
        latency_ms=result.latency_ms,
        model=result.model,
    )

    applied = "none"
    if apply != "none":
        applied = await attach_media(db, entry, media, mode=apply)

    logger.info(
        "cms.illustration.done entry={} media={} bytes={} apply={}",
        entry.id,
        media.id,
        len(data),
        applied,
    )
    return {
        "media_id": media.id,
        "url": media.url,
        # 前端预览要用这个：url 是对象存储内网地址，浏览器直接加载会裂图
        "public_url": public_media_url(media),
        "mime": media.mime,
        "width": media.width,
        "height": media.height,
        "size": media.size,
        "alt": media.alt,
        "prompt": full_prompt,
        "applied": applied,
        "model": result.model,
        "latency_ms": result.latency_ms,
    }


# 云存储的图片处理样式：只缩不放（`>`），1200 宽对正文配图足够。
# 原图 1280×720 约 228KB，缩到 1200 后 104KB，移动端省一半流量。
# `>` 必须写成 %3E —— 裸 `>` 会把 HTML 属性提前闭合。
_CDN_STYLE = "imageMogr2/thumbnail/{}x%3E"


def _is_public_url(url: str) -> bool:
    """判断地址能否被外部读者的浏览器直接解析。

    本地 MinIO 回落（`http://127.0.0.1:9000/...`）和内网段地址写进正文
    就是裂图，这类必须退回代理端点。
    """
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").strip()
    except ValueError:
        return False
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # 域名：按公网处理
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def public_media_url(media: Media, *, width: int = 1200) -> str:
    """正文里可用的媒体地址：优先直连云存储公开地址，内网地址才退回代理端点。

    云存储已配 CDN（当前七牛 `img1.images.023ent.net`，`Cache-Control: max-age=31536000`），
    直连的价值是**请求不再经过后端**：原先正文图走
    `/api/v1/public/media/{id}/thumb`，每刷一次页面后端就要从存储拉原图、
    用 PIL 现缩一张 —— 一个 PV 一次图像计算，七牛 CDN 完全闲置。

    缩图改由 CDN 的图片处理样式承担（`imageMogr2/thumbnail/1200x>`）。
    只有 `media.url` 不可公网访问（本地 MinIO 回落、或尚未配云存储）时，
    才退回代理端点 —— 那条路能用但要省着用。
    """
    url = (media.url or "").strip()
    if url and _is_public_url(url):
        is_image = (media.mime or "").startswith("image/")
        if not (is_image and width):
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{_CDN_STYLE.format(int(width))}"
    return f"/api/v1/public/media/{media.id}/thumb?w={width}"


async def attach_media(
    db: AsyncSession, entry: Entry, media: Media, *, mode: str = "og_image"
) -> str:
    """把已有媒体挂到条目上（og_image / 正文首图）。

    单独成为一个动作，是为了「先生成、看完再决定」这条路径：
    不满意就换一张，满意再挂，不为预览付第二次生成费。
    """
    if mode == "og_image":
        seo = dict(entry.seo or {})
        # 存**站内相对路径**而不是 media.url（对象存储 endpoint）。
        # 两个理由：① `media.url` 是内网地址，社交平台抓到就是空图；
        # ② 域名会换，写死绝对 URL 进库，换域名要洗一遍数据。
        # 绝对化交给渲染层（public_router._render_page_html 的 _abs_url）。
        seo["og_image"] = public_media_url(media)
        entry.seo = seo
    elif mode == "body_head":
        content = dict(entry.content or {})
        html = content.get("text") or ""
        src = public_media_url(media)
        # 旧格式也认：历史正文里插的是 `/api/v1/public/media/{id}/thumb?w=1200`，
        # 只比对新地址会让同一张图被重复插入第二遍。
        legacy = f"/api/v1/public/media/{media.id}/thumb"
        if src in html or media.url in html or legacy in html:
            return "body_head"  # 已经插过，不重复插
        img = (
            f'<img src="{_escape(src)}" alt="{_escape(media.alt or "")}" '
            'style="max-width:100%;height:auto" />'
        )
        content["text"] = f"<p>{img}</p>\n{html}"
        entry.content = content
    elif mode == "none":
        return "none"
    else:
        raise ValueError(f"mode 非法：{mode}")

    entry.updated_at = datetime.now(UTC)
    await db.commit()
    return mode


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


async def list_recent_media(db: AsyncSession, *, limit: int = 12) -> dict[str, Any]:
    """最近生成的配图（前端在生成前给个「上次长什么样」的参考）。"""
    rows = (
        await db.execute(
            select(Media)
            .where(Media.mime.like("image/%"))
            .order_by(Media.id.desc())
            .limit(max(1, min(limit, 50)))
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": m.id,
                "url": m.url,
                "alt": m.alt,
                "width": m.width,
                "height": m.height,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }


def options_meta() -> dict[str, Any]:
    return {
        "aspects": [{"key": k, **v} for k, v in ASPECTS.items()],
        "styles": [{"key": k, "hint": v} for k, v in STYLES.items()],
        "apply_modes": list(APPLY_MODES),
    }
