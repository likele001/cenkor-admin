"""Seed 脚本：初始化默认管理员 + 角色/权限/菜单 + CMS 默认数据"""
from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.apps.cms import models as cms_models
from cenkor_admin.apps.rbac import models as rbac_models
from cenkor_admin.core.db import AsyncSessionLocal, async_engine
from cenkor_admin.core.security import hash_password

log = structlog.get_logger()


# ---- 种子数据 ----
DEFAULT_PERMISSIONS = [
    # CMS
    ("cms:product:read", "API", "查看产品"),
    ("cms:product:write", "API", "编辑产品"),
    ("cms:case:read", "API", "查看案例"),
    ("cms:case:write", "API", "编辑案例"),
    ("cms:news:read", "API", "查看新闻"),
    ("cms:news:write", "API", "编辑新闻"),
    ("cms:site:read", "API", "查看站点配置"),
    ("cms:site:write", "API", "编辑站点配置"),
    # RBAC
    ("rbac:user:read", "API", "查看用户"),
    ("rbac:user:write", "API", "编辑用户"),
    ("rbac:role:read", "API", "查看角色"),
    ("rbac:role:write", "API", "编辑角色"),
    ("rbac:permission:read", "API", "查看权限"),
    ("rbac:menu:read", "API", "查看菜单"),
    ("rbac:menu:write", "API", "编辑菜单"),
    # 媒体
    ("media:upload", "API", "上传媒体"),
    # 系统
    ("system:audit:read", "API", "查看审计日志"),
    # 通知
    ("notification:read", "API", "查看通知列表"),
    ("notification:write", "API", "管理通知"),
    # 前台用户管理
    ("portal:users:read", "API", "查看前台用户"),
    ("portal:users:write", "API", "管理前台用户"),
    # 公告管理
    ("announcements:read", "API", "查看公告"),
    ("announcements:write", "API", "管理公告"),
    # 工单系统
    ("tickets:read", "API", "查看工单"),
    ("tickets:write", "API", "管理工单"),
    ("tickets:assign", "API", "分配工单"),
    # 链接收藏
    ("links:read", "API", "查看链接"),
    ("links:write", "API", "管理链接"),
]

DEFAULT_MENUS = [
    # (key, parent, title, icon, path, sort)
    ("dashboard", None, "Dashboard", "layout-dashboard", "/", 10),
    ("cms", None, "内容管理", "newspaper", None, 50),
    ("cms:products", "cms", "产品", "package", "/cms/products", 51),
    ("cms:cases", "cms", "案例", "briefcase", "/cms/cases", 52),
    ("cms:news", "cms", "新闻", "file-text", "/cms/news", 53),
    ("cms:site", "cms", "站点配置", "settings", "/cms/site", 54),
    ("cms:media", "cms", "媒体库", "image", "/cms/media", 55),
    ("system", None, "系统", "settings-2", None, 90),
    ("system:users", "system", "用户", "users", "/system/users", 91),
    ("system:portal-users", "system", "前台会员", "users", "/system/portal-users", 94),
    ("system:roles", "system", "角色", "shield", "/system/roles", 92),
    ("system:menus", "system", "菜单", "menu", "/system/menus", 93),
    ("system:audit", "system", "审计日志", "history", "/system/audit", 99),
    ("system:notifications", "system", "通知管理", "bell", "/system/notifications", 95),
]

DEFAULT_ROLES = [
    # (code, name, description, is_system, permissions, menus)
    (
        "super_admin", "超级管理员", "拥有所有权限", True,
        [p[0] for p in DEFAULT_PERMISSIONS],  # all
        [m[0] for m in DEFAULT_MENUS],
    ),
    (
        "cms_editor", "内容编辑", "可管理 CMS 内容", False,
        ["cms:product:read", "cms:product:write", "cms:case:read", "cms:case:write",
         "cms:news:read", "cms:news:write", "cms:site:read", "media:upload"],
        ["dashboard", "cms", "cms:products", "cms:cases", "cms:news", "cms:site", "cms:media"],
    ),
    (
        "viewer", "访客", "只读权限", False,
        ["cms:product:read", "cms:case:read", "cms:news:read", "cms:site:read"],
        ["dashboard"],
    ),
]

DEFAULT_USERS = [
    # (email, username, password, nickname, is_superuser, roles)
    ("admin@cenkor.cn", "admin", "admin123", "超级管理员", True, ["super_admin"]),
]

DEFAULT_SITE_CONFIGS = [
    ("brand.name", "辰科", "品牌中文名"),
    ("brand.name_en", "Cenkor", "品牌英文名"),
    ("brand.domain", "cenkor.cn", "主域名"),
    ("brand.tagline", "让企业软件 更简单 更智能", "品牌 tagline"),
    ("brand.description", "辰科（Cenkor）专注企业级软件与 AI 智能化解决方案，为不同行业提供可私有化、可扩展的产品矩阵。", "品牌描述"),
    ("contact.email", "contact@cenkor.cn", "联系邮箱"),
    ("contact.bd_email", "bd@cenkor.cn", "商务合作邮箱"),
    ("contact.support_email", "support@cenkor.cn", "技术支持邮箱"),
]

DEFAULT_PRODUCTS = [
    # (slug, name, chinese_name, tagline, line, stack, desc, features, is_flagship, is_open_source, github, demo, license, sort, website)
    (
        "thinkmes", "ThinkMES", None, "多租户 MES 系统", "manufacturing",
        "ThinkPHP 8 / MySQL / Layui",
        "基于 KeleAdmin 底座的多租户 MES 系统，面向中小型加工厂，覆盖从订单接收到成品出库的全流程。支持多租户隔离、套餐计费、域名绑定，可私有化部署。",
        [
            "订单管理：创建/编辑/跟踪订单，支持批量导入",
            "产品与 BOM：产品库 + 物料清单 + 工艺路线配置",
            "生产计划：排产、工序分配、产能负荷分析",
            "质检管理：质检标准、质检记录、不合格品处理",
            "库存管理：入库/出库/盘点、安全库存预警",
            "采购管理：采购单、供应商管理、采购对账",
            "工资核算：计件/计时工资、工资条、统计报表",
            "数据大屏：产量趋势、良率分析、实时看板",
            "溯源码：一物一码，扫码查询全生产链路",
            "小程序：员工扫码报工、查看工资",
            "多租户：数据隔离、套餐管理、域名绑定",
            "应用中心：按需安装扩展模块"
        ],
        False, False, "https://github.com/likele001/thinkmes", None, None, 1, "https://thinkmes.cenkor.cn",
    ),
    (
        "aisaas", "AIsaas", None, "KeleAdmin SaaS 版", "enterprise",
        "ThinkPHP 8 / MySQL / Composer",
        "基于 KeleAdmin 底座的 SaaS 版本，为企业提供完整的多租户 SaaS 交付能力。内置应用市场，支持租户自助安装业务模块，适合需要快速交付多个租户的场景。",
        [
            "KeleAdmin 多租户底座：数据隔离、租户管理",
            "应用市场：业务模块 zip 上传安装/卸载",
            "套餐计费：套餐配置、订单、续费、升级",
            "RBAC 权限：角色、权限规则、数据权限",
            "安装向导：分步完成环境检测和初始化",
            "私有化部署：支持独立部署到客户服务器"
        ],
        False, False, None, None, None, 2, None,
    ),
    (
        "aitool", "Aitool", None, "AI 工具 + 行业模块平台", "enterprise",
        "ThinkPHP 8 / MySQL / Layui",
        "基于 KeleAdmin 底座的 AI 工具箱，集成 10 个 AI 模块和多个行业垂直模块。AI 模块包括文案生成、代码助手、知识库问答、思维导图、AI 绘画等；行业模块覆盖美业、餐饮、农业、装修等领域。支持应用中心按需安装，可私有化部署。",
        [
            "AI 文案生成：多场景文案一键生成",
            "AI 代码助手：代码补全、解释、重构",
            "AI 知识库 QA：上传文档，智能问答",
            "AI 思维导图：自动生成思维导图",
            "AI 提示词绘画：文字描述生成图片",
            "AI 简历生成：智能简历模板与生成",
            "美业模块：客户记录、排班、项目销售、活动方案",
            "餐饮模块：预约管理、收入记账、员工排班",
            "农业模块：作物日程、视频脚本",
            "装修模块：朋友圈文案、排期管理",
            "RBAC 后台 + 官网 + 用户中心",
            "应用中心：按需安装扩展"
        ],
        False, False, None, None, None, 3, None,
    ),
    (
        "plantflow", "PlantFlow", "厂流", "开源工厂工作流平台（n8n + Dify 双能力）", "ai",
        "React 18 / Vite / React Flow / Express / TypeScript / PostgreSQL / Redis / Docker",
        "开源工厂工作流平台，将 n8n 的可视化工作流编排能力与 Dify 的 AI 应用能力合二为一。支持 Webhook、定时任务、企业微信/飞书消息推送，适合工厂内部自动化和 AI 应用落地。MIT 协议开源，可自由修改和商用。",
        [
            "工作流编辑器：拖拽节点、条件分支、并行执行、子工作流",
            "触发器：手动触发、对话触发、Webhook、定时 Cron、企业微信、飞书",
            "AI 对话：多轮对话、上下文记忆、工具调用",
            "知识库 RAG：文档上传、向量检索、关键词搜索",
            "Agent 工具调用：自定义工具、API 调用",
            "OpenAI 兼容 API：标准 /v1/chat/completions 接口",
            "网页聊天嵌入：一行代码嵌入网站",
            "企业微信/飞书集成：消息推送与回调",
            "执行中心：工作流运行日志、错误追踪",
            "多租户：租户隔离、权限管理",
            "审计日志：操作记录、安全追溯"
        ],
        True, True, "https://github.com/likele001/PlantFlow", "https://api.cloud.cenkor.cn/", "MIT", 1, "https://api.cloud.cenkor.cn",
    ),
    (
        "bizcloud", "商智云 BizCloud", None, "面向本地商家的 AI 自动运营 SaaS", "ai",
        "FastAPI / Vue3 / TypeScript / Element Plus / Vant / Docker",
        "面向本地实体商家的 AI 全自动运营 SaaS 平台。商家 PC、H5、平台管理三端分离部署，AI 自动生成营销内容、管理客户、分析数据，帮助商家降低运营成本。",
        [
            "商家 PC 端：商品管理、订单管理、客户管理、数据看板",
            "H5 移动端：扫码核销、移动下单、消息推送",
            "独立平台管理后台：商家审核、套餐管理、系统配置",
            "FastAPI + Celery 异步任务：后台任务自动处理",
            "讯虎虎皮椒支付：微信/支付宝支付集成",
            "AI 自动内容生成：营销文案、海报、短视频脚本",
            "客户管理：客户画像、消费记录、精准营销",
            "数据报表：销售分析、客流统计、转化率"
        ],
        False, False, None, None, None, 2, None,
    ),
    (
        "openaigw", "OpenAI 兼容聚合网关", None, "带商用计费的 OpenAI 网关", "ai",
        "Python 3.10 / FastAPI / Vue3 / SQLite",
        "对外提供标准 OpenAI 兼容接口的聚合网关，内置 Web 管理后台。支持多渠道模型映射、用户注册、余额计费、套餐管理、虎皮椒支付。适合需要将 AI 能力商业化交付的场景。",
        [
            "OpenAI 兼容接口：标准 /v1/chat/completions",
            "渠道管理：多 API Key 轮询、故障转移",
            "模型映射：自定义模型名称到实际模型的映射",
            "用户系统：注册、登录、API Key 管理",
            "余额计费：按 token 计费、余额充值",
            "套餐管理：预设套餐、自定义套餐",
            "虎皮椒支付：微信/支付宝支付集成",
            "调用日志：请求/响应记录、用量统计",
            "Web 管理后台：渠道、用户、订单、配置一站式管理"
        ],
        False, False, None, None, None, 3, None,
    ),
    (
        "lightmes", "LightMes", None, "轻量化生产管理系统", "manufacturing",
        "FastAPI / Vue3 / Element Plus / Vant4 / MySQL / Celery",
        "为中小型加工厂打造的轻量化、可快速交付的生产管理系统。相比 ThinkMES，LightMes 更轻量、部署更简单，适合快速上线的场景。支持甘特图排产、H5 扫码报工、计件工资核算。",
        [
            "产品管理：产品库、SKU 型号、批量导入",
            "工序管理：工序定义、工艺路线、工序工价",
            "生产计划：甘特图排产（可拖拽）、产能负荷分析",
            "派工管理：按技能派工、二维码标签、设备绑定",
            "扫码报工：H5 扫描任务码、合格/不良数、证据上传",
            "两级审核：班组长初审 → 质检终审",
            "计件工资：审核通过自动计薪、补贴/扣款、工资条",
            "溯源查询：一物一码全链路追溯",
            "仓储库存：入库/出库/盘点、库存预警",
            "采购管理：采购单、入库/退货、对账",
            "CRM：客户档案、联系人、销售机会",
            "ECharts 报表：产量趋势、良率分析、大屏实时刷新"
        ],
        False, False, None, None, None, 1, None,
    ),
]

DEFAULT_CASES = [
    ("智能制造", "某精密机加工企业", "引入 LightMes 后，工序报工效率提升 60%，计件工资核算自动化。", "LightMes", None, 1),
    ("本地零售", "某连锁美妆品牌", "通过商智云实现 AI 自动生成营销内容，月节省运营人力 40%。", "商智云", None, 2),
    ("开源生态", "PlantFlow 厂流", "MIT 协议开源，可私有化部署；Live demo 已在 api.cloud.cenkor.cn 上线。", "PlantFlow", "https://github.com/likele001/PlantFlow", 3),
]


async def main() -> None:
    log.info("seed.starting")
    async with AsyncSessionLocal() as db:
        # ---- 权限 ----
        for code, ptype, name in DEFAULT_PERMISSIONS:
            existing = await db.execute(select(rbac_models.Permission).where(rbac_models.Permission.code == code))
            if not existing.scalar_one_or_none():
                db.add(rbac_models.Permission(code=code, type=ptype, name=name))
        await db.commit()
        log.info("seed.permissions.done", count=len(DEFAULT_PERMISSIONS))

        # ---- 菜单（先建父级）----
        menu_by_key: dict[str, rbac_models.Menu] = {}
        # 第一遍：无 parent 的
        for key, parent_key, title, icon, path, sort in DEFAULT_MENUS:
            if parent_key is None:
                existing = await db.execute(select(rbac_models.Menu).where(rbac_models.Menu.key == key))
                m = existing.scalar_one_or_none()
                if not m:
                    m = rbac_models.Menu(key=key, title=title, icon=icon, path=path, sort=sort)
                    db.add(m)
                    await db.flush()
                menu_by_key[key] = m
        # 第二遍：有 parent 的
        for key, parent_key, title, icon, path, sort in DEFAULT_MENUS:
            if parent_key is not None:
                existing = await db.execute(select(rbac_models.Menu).where(rbac_models.Menu.key == key))
                m = existing.scalar_one_or_none()
                if not m:
                    m = rbac_models.Menu(
                        key=key, parent_id=menu_by_key[parent_key].id,
                        title=title, icon=icon, path=path, sort=sort,
                    )
                    db.add(m)
                    await db.flush()
                menu_by_key[key] = m
        await db.commit()
        log.info("seed.menus.done", count=len(DEFAULT_MENUS))

        # ---- 角色 ----
        perm_cache: dict[str, rbac_models.Permission] = {}
        for code, *_ in DEFAULT_PERMISSIONS:
            p = (await db.execute(select(rbac_models.Permission).where(rbac_models.Permission.code == code))).scalar_one()
            perm_cache[code] = p

        for code, name, desc, is_system, perms, menus in DEFAULT_ROLES:
            existing = await db.execute(select(rbac_models.Role).where(rbac_models.Role.code == code))
            role = existing.scalar_one_or_none()
            if not role:
                role = rbac_models.Role(code=code, name=name, description=desc, is_system=is_system)
                db.add(role)
                await db.flush()

            # 关联权限（幂等：先查再加）
            existing_perms = await db.execute(
                select(rbac_models.RolePermission.permission_id).where(rbac_models.RolePermission.role_id == role.id)
            )
            existing_perm_ids = {row[0] for row in existing_perms.all()}
            for pc in perms:
                pid = perm_cache[pc].id
                if pid in existing_perm_ids:
                    continue
                db.add(rbac_models.RolePermission(role_id=role.id, permission_id=pid))

            # 关联菜单（幂等）
            existing_menus = await db.execute(
                select(rbac_models.RoleMenu.menu_id).where(rbac_models.RoleMenu.role_id == role.id)
            )
            existing_menu_ids = {row[0] for row in existing_menus.all()}
            for mk in menus:
                mid = menu_by_key[mk].id
                if mid in existing_menu_ids:
                    continue
                db.add(rbac_models.RoleMenu(role_id=role.id, menu_id=mid))
        await db.commit()
        log.info("seed.roles.done", count=len(DEFAULT_ROLES))

        # ---- 用户 ----
        for email, username, password, nickname, is_super, role_codes in DEFAULT_USERS:
            existing = await db.execute(select(auth_models.User).where(auth_models.User.email == email))
            user = existing.scalar_one_or_none()
            if not user:
                user = auth_models.User(
                    email=email, username=username,
                    password_hash=hash_password(password),
                    nickname=nickname, is_superuser=is_super,
                )
                db.add(user)
                await db.flush()
            for rc in role_codes:
                role = (await db.execute(select(rbac_models.Role).where(rbac_models.Role.code == rc))).scalar_one()
                # 幂等：已存在就不加
                existing_ur = await db.execute(
                    select(rbac_models.UserRole).where(
                        rbac_models.UserRole.user_id == user.id,
                        rbac_models.UserRole.role_id == role.id,
                    )
                )
                if not existing_ur.scalar_one_or_none():
                    db.add(rbac_models.UserRole(user_id=user.id, role_id=role.id))
        await db.commit()
        log.info("seed.users.done", count=len(DEFAULT_USERS))

        # ---- 站点配置 ----
        for key, value, desc in DEFAULT_SITE_CONFIGS:
            existing = await db.get(cms_models.SiteConfig, key)
            if not existing:
                db.add(cms_models.SiteConfig(key=key, value=value, description=desc))
        await db.commit()
        log.info("seed.site_config.done", count=len(DEFAULT_SITE_CONFIGS))

        # ---- 产品 ----
        for (slug, name, cname, tagline, line, stack, desc, features, is_flagship, is_open_source, github, demo, license, sort, website) in DEFAULT_PRODUCTS:
            existing = await db.execute(select(cms_models.Product).where(cms_models.Product.slug == slug))
            if not existing.scalar_one_or_none():
                db.add(cms_models.Product(
                    slug=slug, name=name, chinese_name=cname, tagline=tagline,
                    line=line, stack=stack, desc=desc, features=features,
                    is_flagship=is_flagship, is_open_source=is_open_source,
                    github_url=github, demo_url=demo, website_url=website,
                    license=license, sort=sort,
                ))
        await db.commit()
        log.info("seed.products.done", count=len(DEFAULT_PRODUCTS))

        # ---- 案例 ----
        for industry, name, desc, tag, href, sort in DEFAULT_CASES:
            existing = await db.execute(select(cms_models.Case).where(cms_models.Case.name == name))
            if not existing.scalar_one_or_none():
                db.add(cms_models.Case(industry=industry, name=name, desc=desc, tag=tag, href=href, sort=sort))
        await db.commit()
        log.info("seed.cases.done", count=len(DEFAULT_CASES))

        # ---- 应用中心：默认安装 CMS ----
        from cenkor_admin.apps.system.models import InstalledApp
        from datetime import datetime, timezone
        from cenkor_admin.apps.cms.manifest import MANIFEST as CMS_MANIFEST

        cms_app = await db.get(InstalledApp, CMS_MANIFEST.key)
        if not cms_app:
            db.add(InstalledApp(
                key=CMS_MANIFEST.key,
                name=CMS_MANIFEST.name,
                version=CMS_MANIFEST.version,
                status="installed",
                installed_at=datetime.now(timezone.utc),
            ))
            await db.commit()
            log.info("seed.apps.cms.installed")

    await async_engine.dispose()
    log.info("seed.done")


if __name__ == "__main__":
    asyncio.run(main())
