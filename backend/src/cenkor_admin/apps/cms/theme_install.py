"""主题包安装 —— 三条入口共用一套落库逻辑。

之前「后台导入」「商店安装」「CLI 打包预演」各写各的，口径漂移只是时间问题：
导入能装的商店拒收，商店装进去的后台不认。抽出来之后只有一份写法。

入口矩阵：

| 入口 | 文件来源 | 校验 | 落库 |
|---|---|---|---|
| ``templates/import``（后台） | 上传 zip | ``validate_package`` | 本模块 |
| ``market_install``（商店） | hub 下载 zip | 同上（require_manifest=True） | 本模块 |
| ``theme_install.install_theme_files`` | 内存 dict | 不重复校验 | 本模块 |
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models, theme_package

logger = logging.getLogger(__name__)

# zip 里允许出现但不写进 cms_templates 的段（Mac 垃圾文件、IDE 元数据）
_SKIP_PARTS = ("__MACOSX", ".DS_Store", "Thumbs.db")


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def kind_of(path: str) -> str:
    """根据路径推断文件类型（写进 cms_templates.kind 供编辑器分组）。"""
    name = path.rsplit("/", 1)[-1]
    if path.startswith("assets/"):
        return "asset"
    if path.startswith("macros/"):
        return "macro"
    if path.startswith("widgets/"):
        return "widget"
    if path.startswith("partials/"):
        return "partial"
    if name.endswith((".json", ".txt")):
        return "meta"
    return {
        "layout.html": "layout",
        "list.html": "list",
        "detail.html": "detail",
        "page.html": "page",
    }.get(name, "partial")


async def invalidate_after_theme_change(
    db: AsyncSession, site_id: int | None, theme: str | None = None
) -> None:
    """模板变更后统一失效：Jinja 模板缓存 + 已落盘静态页。

    版式一动，之前落盘的 HTML 全是旧版，不整站撤掉就会出现
    「后台改了模板，线上还是老样子」——静态化最容易被骂的坑。
    """
    from cenkor_admin.apps.cms import render, static_cache

    render.invalidate_theme_cache(site_id, theme)
    if not static_cache.cache_enabled():
        return
    try:
        if site_id:
            await static_cache.purge_site_by_id(db, site_id)
        else:
            static_cache.purge_all()
    except Exception as exc:
        logger.warning("模板变更后清理静态缓存失败 site_id=%s theme=%s: %s", site_id, theme, exc)


def unzip_theme_package(
    raw: bytes,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """解 zip 只做「读出来 + 去垃圾」，路径安全 / 体积 / 语法 / CSP 全交给公共校验。

    返回 ``(raw_files, too_big)``：``too_big`` 里是体积或编码不合格的文件，
    调用方需要把它跟 ``validate_package().errors`` 合并成一份报错。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"不是合法的 zip 文件：{exc}") from exc

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > theme_package.MAX_PACKAGE_FILES:
        raise ValueError(f"主题包内文件数上限 {theme_package.MAX_PACKAGE_FILES}")

    raw_files: dict[str, str] = {}
    too_big: list[dict[str, str]] = []
    for info in infos:
        name = info.filename.replace("\\", "/")
        if any(part in name for part in _SKIP_PARTS):
            continue
        if info.file_size > theme_package.MAX_FILE_BYTES:
            too_big.append({
                "path": name,
                "message": f"单文件超过 {theme_package.MAX_FILE_BYTES // 1024}KB",
            })
            continue
        try:
            raw_files[name] = zf.read(info).decode("utf-8")
        except UnicodeDecodeError:
            too_big.append({"path": name, "message": "不是 UTF-8 文本"})

    return raw_files, too_big


async def install_theme_files(
    db: AsyncSession,
    *,
    site_id: int,
    theme: str,
    files: dict[str, str],
    overwrite: bool = True,
) -> dict[str, Any]:
    """把已通过校验的文件集写进 ``cms_templates``。

    不做校验 —— 调用方负责先跑 ``validate_package``。半套主题装进去比装不上
    更糟（线上白屏），所以这里是**全量写入**：有任何一个文件写失败，事务回滚。
    """
    existing = set((await db.execute(
        select(models.CmsTemplate.path).where(
            models.CmsTemplate.site_id == site_id,
            models.CmsTemplate.theme == theme,
        )
    )).scalars().all())

    written, skipped = 0, 0
    for path, content in files.items():
        if path in existing:
            if not overwrite:
                skipped += 1
                continue
            row = (await db.execute(
                select(models.CmsTemplate).where(
                    models.CmsTemplate.site_id == site_id,
                    models.CmsTemplate.theme == theme,
                    models.CmsTemplate.path == path,
                )
            )).scalars().first()
            row.content = content
            row.checksum = _md5(content)
            row.kind = kind_of(path)
        else:
            db.add(models.CmsTemplate(
                site_id=site_id, theme=theme, path=path,
                kind=kind_of(path), content=content, checksum=_md5(content),
            ))
        written += 1

    await db.commit()
    await invalidate_after_theme_change(db, site_id, theme)

    return {"written": written, "skipped": skipped}
