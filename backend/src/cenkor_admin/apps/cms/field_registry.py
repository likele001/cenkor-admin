"""FieldRegistry — 字段类型统一注册中心

用于 App 启动时自动注册：
- content_types
- field_groups
- field_definitions
- field_options
- categories_seed

所有 app 的 manifest 通过此接口声明，平台统一处理。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms import models as cms_models
from cenkor_admin.apps.cms.field_types import FIELD_TYPES


class FieldRegistry:
    """字段注册器（单例，通过 get_registry() 访问）"""

    def __init__(self):
        self._registered_keys: set[str] = set()  # 已注册的 field_key（用于去重）

    async def register_content_type(
        self, db: AsyncSession, key: str, name: str, **kwargs
    ) -> cms_models.ContentType:
        """注册或更新一个内容类型"""
        existing = (await db.execute(
            select(cms_models.ContentType).where(cms_models.ContentType.key == key)
        )).scalar_one_or_none()

        if existing:
            existing.name = name
            for k, v in kwargs.items():
                if v is not None and hasattr(existing, k):
                    setattr(existing, k, v)
            return existing

        obj = cms_models.ContentType(
            key=key, name=name,
            icon=kwargs.get("icon"),
            description=kwargs.get("description"),
            supports_category=kwargs.get("supports_category", True),
            supports_tags=kwargs.get("supports_tags", True),
            default_list_template=kwargs.get("default_list_template"),
            default_detail_template=kwargs.get("default_detail_template"),
        )
        db.add(obj)
        await db.flush()
        return obj

    async def register_field_group(
        self, db: AsyncSession, content_type_id: int, key: str, label: str, **kwargs
    ) -> cms_models.FieldGroup:
        """注册一个字段分组"""
        existing = (await db.execute(
            select(cms_models.FieldGroup).where(
                cms_models.FieldGroup.content_type_id == content_type_id,
                cms_models.FieldGroup.key == key,
            )
        )).scalar_one_or_none()

        if existing:
            existing.label = label
            if kwargs.get("sort") is not None:
                existing.sort = kwargs["sort"]
            if kwargs.get("icon"):
                existing.icon = kwargs["icon"]
            return existing

        obj = cms_models.FieldGroup(
            content_type_id=content_type_id,
            key=key, label=label,
            sort=kwargs.get("sort", 0),
            icon=kwargs.get("icon"),
        )
        db.add(obj)
        await db.flush()
        return obj

    async def register_field_definition(
        self,
        db: AsyncSession,
        content_type_id: int,
        field_key: str,
        label: str,
        field_type: str,
        **kwargs,
    ) -> cms_models.FieldDefinition:
        """注册一个字段定义"""
        if field_type not in FIELD_TYPES:
            raise ValueError(f"Invalid field_type: {field_type}")

        existing = (await db.execute(
            select(cms_models.FieldDefinition).where(
                cms_models.FieldDefinition.content_type_id == content_type_id,
                cms_models.FieldDefinition.field_key == field_key,
            )
        )).scalar_one_or_none()

        # 解析 group_id
        group_id = kwargs.get("group_id")
        if group_id is None and kwargs.get("group"):
            group_key = kwargs["group"]
            grp = (await db.execute(
                select(cms_models.FieldGroup).where(
                    cms_models.FieldGroup.content_type_id == content_type_id,
                    cms_models.FieldGroup.key == group_key,
                )
            )).scalar_one_or_none()
            if grp:
                group_id = grp.id

        if existing:
            existing.label = label
            existing.field_type = field_type
            for k in ("required", "default_value", "options", "validation", "sort", "status"):
                v = kwargs.get(k)
                if v is not None:
                    setattr(existing, k, v)
            if group_id is not None:
                existing.group_id = group_id
            return existing

        obj = cms_models.FieldDefinition(
            content_type_id=content_type_id,
            field_key=field_key, label=label, field_type=field_type,
            required=kwargs.get("required", False),
            default_value=kwargs.get("default_value"),
            options=kwargs.get("options"),
            validation=kwargs.get("validation"),
            group_id=group_id,
            sort=kwargs.get("sort", 0),
            status=kwargs.get("status", "active"),
        )
        db.add(obj)
        await db.flush()
        return obj

    async def register_field_option(
        self,
        db: AsyncSession,
        definition_id: int,
        value: str, label: str,
        color: str | None = None, sort: int = 0,
    ) -> cms_models.FieldOption:
        """注册一个字段选项"""
        existing = (await db.execute(
            select(cms_models.FieldOption).where(
                cms_models.FieldOption.definition_id == definition_id,
                cms_models.FieldOption.value == value,
            )
        )).scalar_one_or_none()

        if existing:
            existing.label = label
            if color is not None:
                existing.color = color
            if sort != 0:
                existing.sort = sort
            return existing

        obj = cms_models.FieldOption(
            definition_id=definition_id, value=value, label=label,
            color=color, sort=sort,
        )
        db.add(obj)
        await db.flush()
        return obj

    async def register_category(
        self,
        db: AsyncSession,
        content_type_id: int,
        slug: str, name: str,
        parent_id: int | None = None,
        **kwargs,
    ) -> cms_models.Category:
        """注册一个分类"""
        existing = (await db.execute(
            select(cms_models.Category).where(
                cms_models.Category.content_type_id == content_type_id,
                cms_models.Category.slug == slug,
            )
        )).scalar_one_or_none()

        if existing:
            existing.name = name
            if parent_id is not None:
                existing.parent_id = parent_id
            for k in ("icon", "color", "sort", "status"):
                v = kwargs.get(k)
                if v is not None:
                    setattr(existing, k, v)
            return existing

        obj = cms_models.Category(
            content_type_id=content_type_id,
            parent_id=parent_id,
            slug=slug, name=name,
            icon=kwargs.get("icon"),
            color=kwargs.get("color"),
            sort=kwargs.get("sort", 0),
            status=kwargs.get("status", "active"),
        )
        db.add(obj)
        await db.flush()
        return obj

    async def register_from_manifest(
        self, db: AsyncSession, manifest,
    ) -> dict[str, Any]:
        """从 AppManifest 自动注册所有内容/字段/分类

        Returns:
            {
                "content_types": [id, ...],
                "field_groups": [id, ...],
                "field_definitions": [id, ...],
                "categories": [id, ...],
            }
        """
        result = {
            "content_types": [],
            "field_groups": [],
            "field_definitions": [],
            "categories": [],
        }

        # 1. 注册内容类型
        ct_id_map: dict[str, int] = {}
        for ct_def in manifest.content_types:
            ct = await self.register_content_type(
                db,
                key=ct_def["key"],
                name=ct_def["name"],
                icon=ct_def.get("icon"),
                description=ct_def.get("description"),
                supports_category=ct_def.get("supports_category", True),
                supports_tags=ct_def.get("supports_tags", True),
                default_list_template=ct_def.get("default_list_template"),
                default_detail_template=ct_def.get("default_detail_template"),
            )
            ct_id_map[ct_def["key"]] = ct.id
            result["content_types"].append(ct.id)

        # 2. 注册字段分组（按 content_type 索引）
        fg_id_map: dict[tuple[str, str], int] = {}  # (ct_key, group_key) -> id
        for fg_def in manifest.field_groups:
            ct_key = fg_def.get("content_type")
            if not ct_key or ct_key not in ct_id_map:
                continue
            fg = await self.register_field_group(
                db,
                content_type_id=ct_id_map[ct_key],
                key=fg_def["key"], label=fg_def["label"],
                sort=fg_def.get("sort", 0),
                icon=fg_def.get("icon"),
            )
            fg_id_map[(ct_key, fg_def["key"])] = fg.id
            result["field_groups"].append(fg.id)

        # 3. 注册字段定义
        for fd_def in manifest.field_definitions:
            ct_key = fd_def.get("content_type")
            if not ct_key or ct_key not in ct_id_map:
                continue
            try:
                fd = await self.register_field_definition(
                    db,
                    content_type_id=ct_id_map[ct_key],
                    field_key=fd_def["key"],
                    label=fd_def["label"],
                    field_type=fd_def["type"],
                    group=fd_def.get("group"),
                    required=fd_def.get("required", False),
                    default_value=fd_def.get("default_value"),
                    validation=fd_def.get("validation"),
                    sort=fd_def.get("sort", 0),
                )
                result["field_definitions"].append(fd.id)

                # 注册选项
                for opt in fd_def.get("options", []):
                    if isinstance(opt, str):
                        await self.register_field_option(db, fd.id, opt, opt)
                    elif isinstance(opt, dict):
                        await self.register_field_option(
                            db, fd.id,
                            value=opt["value"], label=opt.get("label", opt["value"]),
                            color=opt.get("color"),
                        )
            except ValueError as e:
                # 跳过无效的字段类型
                print(f"[FieldRegistry] Skip {ct_key}.{fd_def.get('key')}: {e}")

        # 4. 注册分类
        for cat_def in manifest.categories_seed:
            ct_key = cat_def.get("content_type")
            if not ct_key or ct_key not in ct_id_map:
                continue
            await self._seed_category_recursive(
                db, ct_id_map[ct_key], cat_def, parent_id=None, result=result
            )

        await db.commit()
        return result

    async def _seed_category_recursive(
        self, db, ct_id, cat_def, parent_id, result
    ):
        cat = await self.register_category(
            db,
            content_type_id=ct_id,
            slug=cat_def["slug"], name=cat_def["name"],
            parent_id=parent_id,
            icon=cat_def.get("icon"),
            color=cat_def.get("color"),
            sort=cat_def.get("sort", 0),
        )
        result["categories"].append(cat.id)

        for child_def in cat_def.get("children", []):
            await self._seed_category_recursive(db, ct_id, child_def, parent_id=cat.id, result=result)

    async def uninstall_app_data(self, db: AsyncSession, manifest) -> dict[str, int]:
        """卸载 App 时清理其注册的内容/字段/分类数据

        Returns:
            {"content_types": N, "field_definitions": N, "categories": N}
        """
        counts = {"content_types": 0, "field_definitions": 0, "categories": 0}

        # 软删内容类型（级联影响 field_groups/definitions/categories/tags）
        for ct_def in manifest.content_types:
            ct = (await db.execute(
                select(cms_models.ContentType).where(cms_models.ContentType.key == ct_def["key"])
            )).scalar_one_or_none()
            if ct:
                ct.deleted_at = cms_models.func.now()
                counts["content_types"] += 1

        await db.commit()
        return counts


# ============================================================
# 单例
# ============================================================

_registry: FieldRegistry | None = None


def get_registry() -> FieldRegistry:
    global _registry
    if _registry is None:
        _registry = FieldRegistry()
    return _registry


async def register_app(db: AsyncSession, manifest) -> dict[str, Any]:
    """便捷函数：注册一个 app 的所有数据"""
    return await get_registry().register_from_manifest(db, manifest)
