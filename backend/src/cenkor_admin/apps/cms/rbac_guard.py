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
    # 单价决定「花了多少钱」的口径，读要 read，改要 manage
    ("/ai/prices", "cms:ai:read", "cms:ai:manage"),
    ("/ai/providers", "cms:ai:read", "cms:ai:manage"),
    ("/ai/capabilities", "cms:ai:read", "cms:ai:manage"),
    ("/ai/prompts", "cms:ai:read", "cms:ai:manage"),
    # 批量生产会一次消耗大量 token，写操作与「改提示词」同档。
    # 最长前缀匹配，所以 /ai/batch-stats 不会被 /ai/batch 吃掉。
    ("/ai/dashboard", "cms:ai:read", None),
    ("/ai/batch-stats", "cms:ai:read", None),
    ("/ai/batch", "cms:ai:read", "cms:ai:manage"),
    # 重建向量直接烧 token，只给管理员
    ("/ai/vectors/rebuild", None, "cms:ai:manage"),
    # ---------------- AI 业务：产出的是内容，按内容权限管 ----------------
    ("/ai/content-types", "cms:content_types:read", "cms:content_types:write"),
    ("/ai/entries", "cms:entries:read", "cms:entries:write"),
    # 字段级改写（编辑页内嵌）：改的是条目正文，按条目写权限管；
    # 故意不挂 cms:ai:*，否则能给 AI 配 key 的人才有权润色一段话，说不通。
    ("/ai/text", "cms:entries:read", "cms:entries:write"),
    ("/ai/search", "cms:entries:read", None),
    # ---- P2 分批新增的能力：体检 / 问答 / 选题 / 质检 / 配图 ----
    # 这些都是后续批次加进来的端点，最初漏在 _PERM_RULES 之外。
    # 漏配的后果不是「不能用」而是「谁都能用」：守卫只告警然后放行，
    # 于是任何登录角色都能看全站健康报告、跑模型 A/B、生成配图（都在烧钱）。
    ("/ai/health", "cms:entries:read", None),
    # 问答是 POST（问题放 body），写侧同样要码，不能留 None 变成「不设限」
    ("/ai/ask", "cms:ai:read", "cms:ai:read"),
    ("/ai/topic-gaps", "cms:ai:read", None),
    # 跑一次 A/B 是两版并发生成，写侧按 manage 管
    ("/ai/quality/ab", "cms:ai:read", "cms:ai:manage"),
    # 提交盲评结论是编辑的本职工作，不该要求 AI 配置权限
    ("/ai/quality/ab/{run_id}/review", "cms:ai:read", "cms:ai:read"),
    # 人工打分同理：评审不是配置
    ("/ai/quality", "cms:ai:read", "cms:ai:read"),
    # 配图结果落在条目上，按条目权限管；生图费用由套餐额度控制，不叠权限码
    ("/ai/illustration", "cms:entries:read", "cms:entries:write"),
    # 把媒体挂到条目 = 改条目
    ("/ai/media", "media:upload", "media:upload"),
    # 渠道清单是纯只读枚举
    ("/ai/redistribute", "cms:entries:read", None),
    # ---- 发布闭环：排期 / 效果回填 / 渠道分发 ----
    # 看效果数据是内容岗的日常，与「看条目」同档；导入第三方数据、强制重算属写。
    ("/ai/stats", "cms:entries:read", "cms:entries:write"),
    # 渠道凭据（AppID / AppSecret / 封面素材）是系统对接配置，改它比改一篇文章严重，
    # 抬到 ai:manage 一档：能配 AI 的人才能配渠道。
    ("/ai/publish/channels", "cms:entries:read", "cms:ai:manage"),
    # 真正把内容推到外部渠道 = 改变条目的对外可见状态，按条目写权限管。
    ("/ai/publish", "cms:entries:read", "cms:entries:write"),
    # ---- 知识库：上传、删除、重建索引都会改变 AI 的参考语料 ----
    # 读（列表/详情/检索测试）跟看内容同档；写（上传/删除/重建）跟改内容同档。
    # 没有单独设「知识库管理」权限码：能写内容的人本来就在决定团队看什么，
    # 再切一刀只会让配置变复杂而不会真的收紧边界。
    ("/ai/kb", "cms:entries:read", "cms:entries:write"),
    # ---- 落地页 / 官网子站 ----
    # 生成与发布都是对外可见的产出：读=能看内容，写=能上官网。
    # 发布这条尤其要收紧，一个写错的落地页是可以直接投广告烧钱的。
    ("/ai/landing", "cms:entries:read", "cms:entries:write"),
    # ---- Agent 工作流编排 ----
    # 工作流会成批起草内容、并可能挂发布步骤，等于「一次批准，多次产出」。
    # 所以写权限跟条目写权限同档，不额外放宽。
    ("/ai/workflow", "cms:entries:read", "cms:entries:write"),
    # 建模影响面分析（改字段/改类型前看会波及谁）：纯只读
    ("/ai/schema", "cms:content_types:read", None),
    # ---------------- MCP（外部 Agent 的写入口）----------------
    # 这里只有 get_current_user 一层，没有 API Key。漏配规则时守卫直接放行，
    # 等于任何登录用户都能借 MCP 的 publish 工具发内容 —— 必须按条目权限管。
    ("/mcp", "cms:entries:read", "cms:entries:write"),
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
    # 站点增删改是对整个站群的写操作，跟 site-config 同级
    ("/sites", "cms:site:read", "cms:site:write"),
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
