# 自定义标签开发

模板能力不够时，两条路：**模板内 `macro`**（零后端代码，解决重复片段）
和 **App 注册标签**（写 `template_tags.py`，解决新数据源）。

## 一、`macro` — 模板内的自定义标签

重复片段写成宏，这就是模板里的「自定义标签」：

```jinja
{% macro card(item) %}
  <div class="card">
    <a href="{{ item.url }}">{{ item.title }}</a>
    <p>{{ item.excerpt|excerpt(80) }}</p>
  </div>
{% endmacro %}
```

用的时候：

```jinja
{% for r in items %}{{ card(r) }}{% endfor %}
```

跨文件复用：放 `macros/` 目录（如 `macros/card.html`），别处导入：

```jinja
{% from "macros/card.html" import card %}
{% for r in content_list('article', limit=6) %}{{ card(r) }}{% endfor %}
```

宏同样受沙箱约束：不能调内置函数、输出 HTML 要 `|safe`。

## 二、App 注册标签（`template_tags.py`）

需要**新数据源**（查别的表、聚合计算）时，由对应 App 提供。
框架在**启动时自动扫描** `apps/<key>/template_tags.py`，声明即注册，无需改任何别处。

### 文件骨架

```python
"""<你的 App> 的模板标签"""
from __future__ import annotations

from typing import Any

from cenkor_admin.apps.<key> import models
from sqlalchemy import select


def my_list(ctx: Any, limit: int = 10) -> list[dict[str, Any]]:
    """函数标签：第一个参数固定是 ctx（TemplateContext），后面才是模板传的实参。"""
    stmt = select(models.X).limit(max(1, min(int(limit), 50)))
    rows = ctx.session.execute(stmt).scalars().all()
    return [{"id": r.id, "title": r.title} for r in rows]


def my_field(value: Any) -> str:
    """过滤器：标准 Jinja 签名 fn(value, *args)，拿不到 ctx。"""
    return str(value or "").strip()


FUNCTIONS = {"my_list": my_list}
FILTERS = {"my_field": my_field}
```

### 硬性约定

| 项 | 规则 |
|---|---|
| 函数标签签名 | 第一个参数固定 `ctx`（TemplateContext，有 `session`），之后才是模板实参 |
| 过滤器签名 | `fn(value, *args)`，**拿不到 ctx** |
| 名字 | `^[a-z_][a-z0-9_]{0,39}$`，小写字母开头 |
| 撞名 | 撞内置 API、撞其他 App 或同文件重名 → **跳过该条**，日志记 `template_api.rejected`，不抛异常 |
| 沙箱 | 注册成功的函数自动打 `__cms_api__` 标记，模板沙箱据此放行；没有标记的函数照样被拦 |
| 生命周期 | 启动扫描注册；**卸载 App 时自动清理**；停用 App **不摘标签**（模板调用不会报错，返回空） |

### 注册后在哪能看到

- 后台 → CMS → 模板工作台 → 「标签」面板（数据来自 context-api，自动带上 App 标签）
- 文档：[全量速查](/cenkor-admin/template/methods) 的「App 注册标签」一节

### 安全红线

- **只做只读查询**。注册标签等于把执行能力交给所有能编辑模板的人，
  别做写操作、别外呼、别读敏感配置。
- `limit` 一律夹上限（参考 `_clamp` 写法），别让模板把库拖死。
- 返回普通 dict / list，别把 ORM 对象、`_` 开头字段漏出去（沙箱挡 `_` 开头，但别依赖它）。

### 完整参考实现

links 应用是官方范例，见
`backend/src/cenkor_admin/apps/links/template_tags.py`：
函数标签 `links_list`（收藏优先、点击数次之，limit 夹 50）+ 过滤器 `link_domain`。
用法则看[结构标签](/cenkor-admin/template/tag)的友链一节。

## 三、还缺东西？

按顺序：先翻[全量速查](/cenkor-admin/template/methods) →
形式不同就换写法（`|excerpt` 换 `|striptags` 组合）→
重复片段用 `macro` → 真缺数据源再写 `template_tags.py`。
