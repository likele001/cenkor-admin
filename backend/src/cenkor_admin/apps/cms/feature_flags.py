"""站点级自动化开关。

存在 `cms_sites.settings["features"]` 里，不新建表 —— 开关是站点属性，
不是内容数据，单独开一张 KV 表既没有查询价值，又要多一条迁移。
（`cms_site_config` 是全站共享的 KV，没有 site_id，放不了站点级配置。）

默认值全部为 True：保持补齐前的行为，站点不需要任何操作就是「和以前一样」。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models

# key -> 默认值 / 中文名。前端直接读这份 label，不用再维护一份翻译。
FEATURES: dict[str, dict[str, Any]] = {
    "auto_publish": {"default": True, "label": "到点自动发布"},
    "auto_image": {"default": True, "label": "起草时自动配图"},
    "auto_seo": {"default": True, "label": "自动生成 TDK"},
    "auto_push": {"default": True, "label": "发布后自动推送渠道"},
    "auto_translate": {"default": True, "label": "自动翻译"},
}


def defaults() -> dict[str, bool]:
    return {k: bool(cfg["default"]) for k, cfg in FEATURES.items()}


async def _load_site(db: AsyncSession, site_id: int) -> models.Site:
    site = (
        await db.execute(select(models.Site).where(models.Site.id == site_id))
    ).scalar_one_or_none()
    if site is None:
        raise ValueError("站点不存在")
    return site


async def get_features(db: AsyncSession, site_id: int) -> dict[str, bool]:
    """读站点开关；没配过的键回落默认值。"""
    site = await _load_site(db, site_id)
    raw = dict((site.settings or {}).get("features") or {})
    return {
        key: bool(raw.get(key, cfg["default"]))
        for key, cfg in FEATURES.items()
    }


async def is_feature_enabled(db: AsyncSession, site_id: int | None, key: str) -> bool:
    """给后台任务用的单键判断：站点取不到就当开着，不让配置问题卡住调度。"""
    if site_id is None:
        return True
    if key not in FEATURES:
        return True
    try:
        feats = await get_features(db, site_id)
    except ValueError:
        return True
    return feats[key]


async def set_features(
    db: AsyncSession, site_id: int, patch: dict[str, bool]
) -> dict[str, bool]:
    """按 patch 覆盖指定开关，其余保持不变。"""
    unknown = set(patch) - set(FEATURES)
    if unknown:
        raise ValueError(f"未知开关：{', '.join(sorted(unknown))}")

    site = await _load_site(db, site_id)
    settings = dict(site.settings or {})
    feats = dict(settings.get("features") or {})
    for key, value in patch.items():
        feats[key] = bool(value)
    settings["features"] = feats
    # JSON 列是原地可变对象，必须整体重新赋值，否则 SQLAlchemy 检测不到变更
    site.settings = settings
    await db.commit()
    await db.refresh(site)
    return await get_features(db, site_id)
