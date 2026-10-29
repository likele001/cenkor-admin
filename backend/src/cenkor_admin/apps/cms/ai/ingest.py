"""素材直入 —— 把上传的附件解析成可喂给起草链路的文本。

三条原则：

1. 解析层只管「附件 → 文本」，起草仍走 ``copilot.draft_entry``，不重复实现一套
2. 能用本地库解析的绝不花 token（PDF / Word / Excel / 纯文本）
3. 必须看图的才走 vision（图片 / 视频抽帧 / 扫描版 PDF），并写生成溯源

硬上限：单文件 20MB、单文件文本 20000 字、合并后 30000 字。超限截断并在
``warnings`` 里说明，不静默丢内容。
"""
from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CHARS_PER_FILE = 20_000
MAX_CHARS_TOTAL = 30_000
MAX_PDF_PAGES = 80
MAX_SHEET_ROWS = 200
VISION_MAX_EDGE = 1568
VISION_FRAMES = 3

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
_PLAIN_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".yaml", ".yml"}
_HTML_EXT = {".html", ".htm"}

# 图片：既要转录文字，也要描述画面——产品照/现场照的价值往往在图里不在字里
_IMAGE_PROMPT = (
    "请把这张图片转成结构化文本，用于后续撰写文章素材：\n"
    "1. 如果图中有文字（标签、铭牌、参数表、表格、标题），**逐字完整转录**，保留原有层级与数字\n"
    "2. 描述画面主体：是什么产品/场景/设备，可见的外观特征、材质、颜色、型号标识\n"
    "3. 如果是图表，说明图表类型、坐标含义与关键数据点\n"
    "只输出信息本身，不要客套话，不要评价图片质量。图中确实没有的信息不要编。"
)

_VIDEO_PROMPT = (
    "这些是一个视频的 {n} 个关键帧（按时间顺序）。请输出结构化文本：\n"
    "1. 概括视频讲了什么（场景/主题/事件）\n"
    "2. 逐帧描述画面内容，**转录每一帧里出现的所有文字**\n"
    "3. 如果有产品、设备、参数、价格等硬信息，单独列出\n"
    "只输出信息本身，不要编造帧里没有的内容。"
)


@dataclass
class ExtractResult:
    filename: str
    kind: str
    text: str
    chars: int = 0
    pages: int | None = None
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "kind": self.kind,
            "chars": self.chars or len(self.text),
            "pages": self.pages,
            "truncated": self.truncated,
            "warnings": self.warnings,
            "meta": self.meta,
            "text": self.text,
        }


def _cap(text: str, limit: int = MAX_CHARS_PER_FILE) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip() + "\n…（内容过长，已截断）", True


# ---------------------------------------------------------------- PDF
def _pdf_sync(path: Path) -> tuple[str, int, bool, float]:
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        pages = doc.page_count
        chunks: list[str] = []
        for i in range(min(pages, MAX_PDF_PAGES)):
            try:
                raw = doc[i].get_text("text") or ""
            except Exception:  # noqa: BLE001 —— 单页坏了不该拖垮整个文件
                continue
            body = raw.strip()
            if body:
                chunks.append(f"【第{i + 1}页】\n{body}")
        text = "\n\n".join(chunks)
        density = len(text) / max(1, min(pages, MAX_PDF_PAGES))
        return text, pages, pages > MAX_PDF_PAGES, density
    finally:
        doc.close()


def _pdf_render(path: Path, page_idx: list[int], dpi: int = 150) -> list[Path]:
    import pymupdf

    out: list[Path] = []
    doc = pymupdf.open(str(path))
    try:
        for i in page_idx:
            if i >= doc.page_count:
                break
            pix = doc[i].get_pixmap(dpi=dpi)
            p = path.parent / f"_page{i + 1}.png"
            pix.save(str(p))
            out.append(p)
    finally:
        doc.close()
    return out


async def _pdf(session: AsyncSession, path: Path, filename: str, created_by: int | None) -> ExtractResult:
    text, pages, page_capped, density = await asyncio.to_thread(_pdf_sync, path)
    warns: list[str] = []
    if page_capped:
        warns.append(f"PDF 共 {pages} 页，只解析前 {MAX_PDF_PAGES} 页")

    # 文字密度过低 = 扫描件（产品手册/合同常见），转图做 OCR，否则等于没解析
    if density < 80 and pages:
        picked = list(range(min(pages, 6)))
        imgs = await asyncio.to_thread(_pdf_render, path, picked)
        if imgs:
            ocr = await _vision(
                session,
                [str(p) for p in imgs],
                _VIDEO_PROMPT.format(n=len(imgs)).replace("视频的关键帧", "扫描版 PDF 的页面"),
                kind="ingest_ocr",
                target=f"file:{filename}",
                created_by=created_by,
            )
            if ocr:
                text = (text + "\n\n【以下为扫描件 OCR】\n" + ocr).strip()
                warns.append(f"疑似扫描件，已对前 {len(imgs)} 页做 OCR")

    text, truncated = _cap(text)
    if truncated:
        warns.append(f"文本超过 {MAX_CHARS_PER_FILE} 字，已截断")
    return ExtractResult(filename, "pdf", text, pages=pages, truncated=truncated, warnings=warns)


# ---------------------------------------------------------------- DOCX
def _docx_sync(path: Path) -> tuple[str, int]:
    import docx

    d = docx.Document(str(path))
    parts: list[str] = []
    for p in d.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    for ti, table in enumerate(d.tables):
        rows: list[str] = []
        for row in table.rows:
            cells = [(c.text or "").strip().replace("\n", " ") for c in row.cells]
            if any(cells):
                rows.append(" | ".join(cells))
        if rows:
            parts.append(f"【表 {ti + 1}】\n" + "\n".join(rows[:MAX_SHEET_ROWS]))
    return "\n".join(parts), len(d.tables)


async def _docx(path: Path, filename: str) -> ExtractResult:
    text, n_tables = await asyncio.to_thread(_docx_sync, path)
    warns: list[str] = []
    if n_tables:
        warns.append(f"含 {n_tables} 个表格，已转成竖线分隔文本")
    text, truncated = _cap(text)
    if truncated:
        warns.append(f"文本超过 {MAX_CHARS_PER_FILE} 字，已截断")
    return ExtractResult(filename, "docx", text, truncated=truncated, warnings=warns)


# ---------------------------------------------------------------- XLSX
def _xlsx_sync(path: Path) -> tuple[str, int]:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        parts: list[str] = []
        for ws in wb.worksheets:
            rows: list[str] = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= MAX_SHEET_ROWS:
                    rows.append(f"…（仅取前 {MAX_SHEET_ROWS} 行）")
                    break
                cells = ["" if v is None else str(v) for v in row]
                if any(c.strip() for c in cells):
                    rows.append(" | ".join(cells))
            if rows:
                parts.append(f"【工作表 {ws.title}】\n" + "\n".join(rows))
        return "\n\n".join(parts), len(wb.worksheets)
    finally:
        wb.close()


async def _xlsx(path: Path, filename: str) -> ExtractResult:
    text, n_sheets = await asyncio.to_thread(_xlsx_sync, path)
    warns = [f"共 {n_sheets} 个工作表，每表最多取 {MAX_SHEET_ROWS} 行"] if n_sheets else []
    text, truncated = _cap(text)
    if truncated:
        warns.append(f"文本超过 {MAX_CHARS_PER_FILE} 字，已截断")
    return ExtractResult(filename, "xlsx", text, truncated=truncated, warnings=warns)


# ---------------------------------------------------------------- 纯文本 / HTML
def _decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_BREAK_RE = re.compile(r"</?(p|div|br|li|tr|h[1-6])[^>]*>", re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def _html_text(raw: str) -> str:
    s = _TAG_RE.sub("", raw)
    s = _BREAK_RE.sub("\n", s)
    s = _ANY_TAG_RE.sub("", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def _plain(data: bytes, filename: str, kind: str = "text") -> ExtractResult:
    text, truncated = _cap(_decode(data))
    warns = [f"文本超过 {MAX_CHARS_PER_FILE} 字，已截断"] if truncated else []
    return ExtractResult(filename, kind, text, truncated=truncated, warnings=warns)


# ---------------------------------------------------------------- 图片 / 视频
def _shrink(path: Path) -> Path:
    """大图先缩到视觉模型的常规边长，省 token 也省时间。"""
    from PIL import Image

    try:
        im = Image.open(path)
    except Exception:  # noqa: BLE001 —— 打不开就原样交给下游报错
        return path
    if max(im.size) <= VISION_MAX_EDGE:
        return path
    im.thumbnail((VISION_MAX_EDGE, VISION_MAX_EDGE))
    out = path.with_name(path.stem + "_s.png")
    im.convert("RGB").save(out, "PNG")
    return out


def _probe_duration(path: Path) -> float:
    try:
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float((p.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _grab_frames(path: Path, n: int = VISION_FRAMES) -> list[Path]:
    dur = _probe_duration(path)
    if dur <= 0:
        return []
    out: list[Path] = []
    for i in range(n):
        ts = dur * (i + 1) / (n + 1)
        f = path.parent / f"_f{i + 1}.jpg"
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{max(0.1, ts):.2f}", "-i", str(path),
                 "-frames:v", "1", "-q:v", "3", str(f)],
                capture_output=True, timeout=120, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if f.is_file() and f.stat().st_size:
            out.append(f)
    return out


async def _vision(
    session: AsyncSession,
    images: list[str],
    prompt: str,
    *,
    kind: str,
    target: str,
    created_by: int | None,
) -> str:
    from cenkor_admin.apps.cms.ai import copilot
    from cenkor_admin.core.llm import get_llm_for

    llm = get_llm_for("vision")
    try:
        res = await llm.vision_chat(prompt, images, max_tokens=2000)
    except Exception as exc:  # noqa: BLE001 —— 识别失败要让上层知道，但不能吞掉素材
        await copilot._record(
            session, kind=kind, target=target, result=None,
            status="failed", error=str(exc)[:500], created_by=created_by, prompt=prompt,
        )
        raise
    await copilot._record(
        session, kind=kind, target=target, result=res,
        created_by=created_by, prompt=prompt,
    )
    return (res.text or "").strip()


async def _image(
    session: AsyncSession, path: Path, filename: str, created_by: int | None
) -> ExtractResult:
    small = await asyncio.to_thread(_shrink, path)
    text = await _vision(
        session, [str(small)], _IMAGE_PROMPT,
        kind="ingest_image", target=f"file:{filename}", created_by=created_by,
    )
    text, truncated = _cap(text)
    return ExtractResult(filename, "image", text, truncated=truncated,
                         meta={"size": path.stat().st_size})


async def _video(
    session: AsyncSession, path: Path, filename: str, created_by: int | None
) -> ExtractResult:
    frames = await asyncio.to_thread(_grab_frames, path)
    if not frames:
        raise ValueError("视频抽帧失败，可能是编码不受支持或文件损坏")
    frames_small = [str(await asyncio.to_thread(_shrink, f)) for f in frames]
    text = await _vision(
        session, frames_small, _VIDEO_PROMPT.format(n=len(frames_small)),
        kind="ingest_video", target=f"file:{filename}", created_by=created_by,
    )
    text, truncated = _cap(text)
    return ExtractResult(
        filename, "video", text, truncated=truncated,
        meta={"frames": len(frames_small), "duration": round(_probe_duration(path), 2)},
    )


# ---------------------------------------------------------------- 入口
async def extract_attachment(
    session: AsyncSession,
    data: bytes,
    filename: str,
    *,
    created_by: int | None = None,
) -> ExtractResult:
    """解析单个附件。不支持的格式抛 ``ValueError``（调用方转 400）。"""
    if not data:
        raise ValueError(f"{filename} 是空文件")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"{filename} 超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")

    ext = Path(filename or "").suffix.lower()
    tmpdir = Path(tempfile.mkdtemp(prefix="cms-ingest-"))
    path = tmpdir / f"attach{ext or '.bin'}"
    path.write_bytes(data)
    try:
        if ext == ".pdf":
            return await _pdf(session, path, filename, created_by)
        if ext == ".docx":
            return await _docx(path, filename)
        if ext in (".xlsx", ".xlsm"):
            return await _xlsx(path, filename)
        if ext in _IMAGE_EXT:
            return await _image(session, path, filename, created_by)
        if ext in _VIDEO_EXT:
            return await _video(session, path, filename, created_by)
        if ext in _HTML_EXT:
            text, truncated = _cap(_html_text(_decode(data)))
            return ExtractResult(
                filename, "html", text, truncated=truncated,
                warnings=[f"文本超过 {MAX_CHARS_PER_FILE} 字，已截断"] if truncated else [],
            )
        if ext in _PLAIN_EXT or not ext:
            return _plain(data, filename)
        if ext == ".doc":
            raise ValueError(f"{filename}：不支持 .doc 老格式，请另存为 .docx")
        raise ValueError(f"{filename}：不支持的格式 {ext}（支持 PDF/Word/Excel/图片/视频/文本）")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def build_brief(results: list[ExtractResult], note: str = "") -> str:
    """把多份素材拼成起草用的 brief。总量超限时截断并标注。"""
    parts: list[str] = []
    if note.strip():
        parts.append(f"【用户说明】\n{note.strip()}")
    for r in results:
        if r.text.strip():
            parts.append(f"【素材：{r.filename}】\n{r.text.strip()}")
    merged = "\n\n".join(parts).strip()
    if len(merged) > MAX_CHARS_TOTAL:
        merged = merged[:MAX_CHARS_TOTAL].rstrip() + "\n\n…（素材总量超限，已截断）"
    return merged
