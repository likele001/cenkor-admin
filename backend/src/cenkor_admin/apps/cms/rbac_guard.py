"""CMS 细分权限守卫（覆盖整个 `/cms` 前缀）。

## 为什么需要

`api/v1/__init__.py` 里 `/cms` 下的路由 include 时只挂了
`Depends(get_current_user)` —— 那只是「登录校验」，不区分「谁」。结果：
任何能登录后台的账号都能改内容类型定义、批量删条目、改站点字段、调 AI 重建向量。

逐个端点挂 `require_permission()` 不可行：60+ 个端点，加一个忘一个，
漏掉的那个就是一条无人看管的写入口。所以这里用一张
「路由模板 → (读权限, 写权限)」的表在 **router 级**统一拦截，
新端点自动继承，不需要谁记得加装饰器。

## 覆盖范围

挂载在 `/cms` 下的 6 个 router，除 MCP 外全部覆盖：

| router | 覆盖 | 说明 |
|---|---|---|
| `cms_router`（旧三条线 + 站点 + 媒体） | ✅ | cases / news / site-config / media / products |
| `content_engine_router`（V2） | ✅ | 建模 / 分类标签 / 条目 / 语言 / 搜索 |
| `cms_ai_router` | ✅ | AI 产出内容，按内容权限走；密钥类按 `cms:ai:*` |
| `template_router` | ✅ | 模板渲染改站点呈现，归 `cms:site:*` |
| `graphql_router` | ✅ | `graphql.py` 无 mutation，按条目读权限兜底 |
| `cms_mcp_router` | ❌ | 鉴权走 `MCP_API_KEY`，套登录依赖会把 Agent 挡在门外 |

## 匹配方式

用的是 FastAPI 注册的**路由模板**（`/api/v1/cms/entries/{entry_id}/review`），
不是实际 URL —— 模板里没有具体 id，规则才能写成前缀。按最长前缀匹配，
所以 `/entries/{entry_id}/review` 不会被 `/entries` 吃掉，`/ai/entries/...`
也不会被 `/entries` 吃掉。

## fail-open 的取舍

未命中任何规则时**放行**并打 `cms.rbac.unmapped` 告警。

理由：漏配一条规则的后果应该是「那个端点暂时没保护」，而不是「整片接口 403」。
线上 403 是事故，漏保护是待办。日志里的 path 就是待补的规则，
`verify_guard_map.py` 这类穷举脚本能在发布前把漏配抓出来。

## 开关

`CMS_RBAC_ENFORCE`（默认 true）。出问题时可临时置 false 退回「登录即可」。
"""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException, Request

from cenkor_admin.api.deps import get_current_user, user_has_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.config import get_settings

# 必须用 structlog：守卫里的日志带结构化 kwargs（path/method/perm），
# 标准库 Logger 不支持，会 TypeError -> 403 变成 500。
log = structlog.get_logger(__name__)

# CMS 的挂载前缀（main.py 挂 /api/v1，api/v1/__init__.py 再挂 /cms）
_MOUNT_MARK = "/cms/"
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# (路由模板, 读权限, 写权限)
# 权限为 None = 该方向不设限。顺序无关，按最长前缀匹配。
_PERM_RULES: tuple[tuple[str, str | None, str | None], ...] = (
    # ---------------- AI 管理 ----------------
    # admin_router 已自带 require_permission(cms:ai:read/manage)，
    # 这里用同一组码再兜一层：两边必须一致，否则「守卫生效、admin_router 没挂」
    # 或者反过来，都会留下一条只差一个 include 就能绕过的口子。
    ("/ai/overview", "cms:ai:read", None),
    ("/ai/presets", "cms:ai:read", None),
    ("/ai/usage", "cms:ai:read", None),
    ("/ai/providers", "cms:ai:read", "cms:ai:manage"),
    ("/ai/capabilities", "cms:ai:read", "cms:ai:manage"),
    # 重建向量直接烧 token，只给管理员
    ("/ai/vectors/rebuild", None, "cms:ai:manage"),
    # ---------------- AI 业务：产出的是内容，按内容权限管 ----------------
    ("/ai/content-types", "cms:content_types:read", "cms:content_types:write"),
    ("/ai/entries", "cms:entries:read", "cms:entries:write"),
    # 字段级改写（编辑页内嵌）：改的是条目正文，按条目写权限管；
    # 故意不挂 cms:ai:*，否则能给 AI 配 key 的人才有权润色一段话，说不通。
    ("/ai/text", "cms:entries:read", "cms:entries:write"),
    ("/ai/search", "cms:entries:read", None),
    # ---------------- 内容引擎：建模三件套 ----------------
    # 字段组 / 字段定义 / 选项统一归 field_definitions。
    # 显式排在 /content-types 前面，让「改字段要 field_definitions 权限而不是
    # content_types」一眼可见（虽然最长匹配本来也能赢）。
    (
        "/content-types/{ct_id}/field-groups",
        "cms:field_definitions:read",
        "cms:field_definitions:write",
    ),
    (
        "/content-types/{ct_id}/field-definitions",
        "cms:field_definitions:read",
        "cms:field_definitions:write",
    ),
    ("/field-definitions", "cms:field_definitions:read", "cms:field_definitions:write"),
    ("/field-options", "cms:field_definitions:read", "cms:field_definitions:write"),
    # 字段类型清单是纯只读枚举
    ("/field-types", "cms:content_types:read", None),
    ("/content-types", "cms:content_types:read", "cms:content_types:write"),
    # ---------------- 内容引擎：分类 / 标签 / 语言 ----------------
    ("/categories", "cms:categories:read", "cms:categories:write"),
    ("/tags", "cms:tags:read", "cms:tags:write"),
    # 语言是条目字段级元数据，跟着 entries 走
    ("/languages", "cms:entries:read", "cms:entries:write"),
    # ---------------- 条目 ----------------
    # 审核独立于编辑：能提交（entries:write）不等于能通过（entry:review）。
    # 读侧给 None —— 审核日志走 /entries/{id}/review-log，由 /entries 规则接管。
    ("/entries/{entry_id}/review", None, "cms:entry:review"),
    ("/entries", "cms:entries:read", "cms:entries:write"),
    # 搜索是条目的读视图，不单开权限码（多一个码就多一处要配）
    ("/search", "cms:entries:read", None),
    # ---------------- 旧三条线 ----------------
    ("/products", "cms:product:read", "cms:product:write"),
    ("/cases", "cms:case:read", "cms:case:write"),
    ("/news", "cms:news:read", "cms:news:write"),
    # ---------------- 站点与模板 ----------------
    # 模板渲染决定对外呈现，等价于改站点配置
    ("/site-config", "cms:site:read", "cms:site:write"),
    ("/templates", "cms:site:read", "cms:site:write"),
    # ---------------- 媒体 ----------------
    # 库里只有 media:upload 一个码（前端路由守卫也用这个），读写共用
    ("/media", "media:upload", "media:upload"),
    # ---------------- GraphQL ----------------
    # graphql.py 只有 query、没有 mutation，按条目读权限兜底。
    # 写侧给 entries:write 纯属防御：将来加了 mutation 也不至于只凭读权限就能写。
    ("/graphql", "cms:entries:read", "cms:entries:write"),
)


def relative_route_path(route_path: str) -> str:
    """剥掉挂载前缀，只留 CMS 自己的路径。"""
    idx = route_path.find(_MOUNT_MARK)
    if idx >= 0:
        return route_path[idx + len(_MOUNT_MARK) - 1 :]
    if route_path.endswith("/cms"):
        return "/"
    return route_path


def resolve_cms_permission(route_path: str, method: str) -> tuple[bool, str | None]:
    """把 (路由模板, HTTP 方法) 解析成权限码。

    返回值：
      ``(False, None)``  未命中任何规则 → 调用方放行并告警
      ``(True,  None)``  命中规则但该方向不设限 → 放行
      ``(True,  code)``  命中规则 → 需要校验 code
    """
    rel = relative_route_path(route_path)
    is_write = method.upper() in _WRITE_METHODS

    best: tuple[str, str | None, str | None] | None = None
    for rule in _PERM_RULES:
        base = rule[0]
        if rel != base and not rel.startswith(base + "/"):
            continue
        if best is None or len(base) > len(best[0]):
            best = rule

    if best is None:
        return False, None
    return True, (best[2] if is_write else best[1])


async def cms_permission_guard(
    request: Request,
    user: auth_models.User = Depends(get_current_user),
) -> None:
    """router 级守卫：一次挂载覆盖整个 `/cms` 前缀。"""
    if not getattr(get_settings(), "CMS_RBAC_ENFORCE", True):
        return

    route = request.scope.get("route")
    route_path = getattr(route, "path", None) or request.url.path

    matched, code = resolve_cms_permission(route_path, request.method)
    if not matched:
        log.warning(
            "cms.rbac.unmapped",
            path=route_path,
            method=request.method,
            hint="未匹配 _PERM_RULES，已放行；请补权限规则",
        )
        return
    if code is None:
        return
    if not user_has_permission(user, code):
        log.info(
            "cms.rbac.denied",
            path=route_path,
            method=request.method,
            code=code,
            user_id=getattr(user, "id", None),
        )
        raise HTTPException(status_code=403, detail=f"无权限：{code}")
