"""多渠道再分发：一篇长文 → 各渠道各自的语言。

## 为什么不是「复制粘贴」

同一篇内容发到公众号、小红书、LinkedIn，效果差得离谱，原因不在内容，在**体裁**：

- 公众号：读者点进来是「我订阅了，愿意读」，可以长、要有小标题、结尾要引导关注
- 小红书：feed 流里 3 秒决定划不划走，必须短句、要 emoji 分段、话题标签决定分发
- LinkedIn：职业社交场，要第一人称洞察 + 可讨论的观点，忌营销腔

直接把长文贴到小红书，等于把一篇报告塞进电梯广告位。

## 边界（重要）

这里**只产出改写后的文本，不调平台 API 推送**：
1. 公众号需要已认证的 appid/secret + IP 白名单，凭据不在系统里
2. 小红书没有开放的发文接口，第三方工具走的是模拟登录，违反平台条款
3. 平台内容审核存在封号风险，机器自动发不是可以默认帮用户做的决定

所以：**改写这件事自动化，发布这件事留给人**。产出可直接复制/导出，
配上标题、标签、钩子、CTA 这些渠道必需件，人工过一眼再发。

## 一处刻意的设计

`notes` 字段要求模型说明「改了什么、为什么」—— 因为改写最大的风险是
**悄悄丢了事实或加了没说过的话**。让人一眼看到模型的调整理由，
比事后人肉比对原文快得多。
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.apps.cms.ai import prompt_registry as prompts
from cenkor_admin.apps.cms.ai.copilot import _as_object, _record
from cenkor_admin.apps.cms.ai.rag import _extract_body, _strip_html
from cenkor_admin.apps.cms.models import Entry
from cenkor_admin.core.llm import LLMError, get_llm

_KIND_REDISTRIBUTE = "redistribute"

# 长文改写是系统里最慢的一类生成：公众号正文 800~1500 字，实测单次
# 90~200 秒（推理模型的思考过程与正文共享预算）。
# 用默认 60s 会稳定 ReadTimeout —— 而且重试毫无价值：同一个 prompt 再发一遍
# 只会再等一个 60 秒，最后报出来的是一句冒号后空白的错误。
# 因此这里显式放大超时，并把重试关掉（timeout 已经给足，重试只延长用户等待）。
_REDIST_TIMEOUT = 300.0
_REDIST_RETRIES = 0

# 渠道规格：用来做长度约束与产物校验
CHANNELS: dict[str, dict[str, Any]] = {
    "wechat": {
        "label": "微信公众号",
        "limit": 4000,
        "min_chars": 600,
        "hint": "长文，正文 800~1500 字（不要超过 2000 字）；保留小标题结构（用 ## 二级标题），"
        "开头 2 行内给出读者收益，结尾一句自然的关注/在看引导；不要用 emoji 刷屏，最多 2 个",
    },
    "xiaohongshu": {
        "label": "小红书",
        "limit": 1000,
        "min_chars": 150,
        "hint": "口语化短句，一句一行，每段 1~2 行；适度 emoji 分段（每段开头 1 个）；"
        "标题要有具体利益点或反差；结尾 4~6 个话题标签（#开头）",
    },
    "linkedin": {
        "label": "LinkedIn",
        "limit": 3000,
        "min_chars": 300,
        "hint": "第一人称职业视角，先抛一个具体观察或反常识结论，再给 2~3 条可迁移的经验；"
        "语气克制专业，禁止营销体和感叹号堆叠；结尾 3~5 个话题标签（#开头）",
    },
}

_REDISTRIBUTE_SYSTEM = """你是跨渠道内容改编专家。把一篇长文改写成指定渠道的体裁。

只输出一个 JSON 对象（以 { 开头、以 } 结尾），不要数组、不要解释文字：
{
  "title": "该渠道的标题（小红书要有钩子，公众号可正式，LinkedIn 可用结论式）",
  "hook": "开头第一句/第一行，负责让人不划走",
  "body": "正文（纯文本，用换行分段；公众号可用 ## 小标题，小红书用短句+换行）",
  "tags": ["话题标签，不含 # 号"],
  "notes": "你改了什么、为什么这么改（2~3 句，给人核对事实用）"
}

铁律：
1. **不许编造原文没有的事实、数字、案例**。原文没说的，宁可不写
2. 不许把原文的具体结论改成模糊表述（「显著降低」不能变成「有一定效果」）
3. 各渠道字数上限必须遵守，超了就是废稿
4. 不要输出 Markdown 代码块，body 里不要出现 ```
5. **body 只能是成品正文**。禁止出现对原文的评论或元叙述 ——
   比如「原文重复了 8 遍」「上面这段话」「本文的意思是」「内容较单薄」。
   你对原文的任何意见、改动说明，一律写进 notes 字段，不要写进 body
6. 原文若有缺陷（重复、空洞、缺数据），按它想表达的意思**正常改写**，不要点评缺陷
7. **话题标签只放 tags 字段，body 里一个 # 都别出现**。body 末尾不要写「#tag #tag」——
   系统会单独渲染标签，重复出现会被用户当成系统 bug"""


def _channel_spec(channel: str) -> dict[str, Any]:
    spec = CHANNELS.get(channel)
    if spec is None:
        raise LLMError(f"不支持的渠道：{channel}（可选：{'/'.join(CHANNELS)}）")
    return spec


async def redistribute_entry(
    session: AsyncSession,
    entry: Entry,
    *,
    channel: str,
    lang: str = "zh-CN",
    created_by: int | None = None,
) -> dict[str, Any]:
    """把一条内容改写成指定渠道体裁。**只返回结果，不写库。**"""
    spec = _channel_spec(channel)
    llm = get_llm()

    body_raw = _extract_body(entry.content or {})
    body_text = _strip_html(body_raw)[:6000]
    if not body_text.strip():
        raise LLMError("该条目没有正文，无法再分发")

    user_msg = (
        f"目标渠道：{spec['label']}\n"
        f"体裁要求：{spec['hint']}\n"
        f"字数上限：{spec['limit']} 字（正文 body 部分）\n"
        f"输出语言：{lang}\n\n"
        f"原标题：{entry.title}\n"
        f"原文正文：\n{body_text}\n\n"
        f"摘要：{str((entry.seo or {}).get('description') or '')[:300]}"
    )
    messages = [
        {"role": "system", "content": await prompts.get(session, "redistribute", _REDISTRIBUTE_SYSTEM)},
        {"role": "user", "content": user_msg},
    ]

    try:
        # 预算给足：当前绑定的可能是推理模型，思考过程与正文共享 max_tokens。
        # 2400 会被 reasoning 吃光、正文为空；6000 仍会偶发截断（实测 reasoning
        # 单次可到 2 万字符，公众号长文最先崩）。
        # 正文目标已压到 800~1500 字，所以抬预算不会再拉长耗时，只是防截断。
        raw, result = await llm.chat_json(
            messages,
            temperature=0.5,
            max_tokens=12000,
            timeout=_REDIST_TIMEOUT,
            max_retries=_REDIST_RETRIES,
        )
    except Exception as exc:
        await _record(
            session,
            kind=_KIND_REDISTRIBUTE,
            target=f"entry:{entry.id}:{channel}",
            result=None,
            status="failed",
            error=str(exc),
            created_by=created_by,
            prompt=user_msg,
        )
        raise

    obj = _as_object(raw, "再分发")

    body = str(obj.get("body") or "").strip()
    # 模型有时把话题标签同时写进 body 尾部，会和独立渲染的 tags 重复
    body, tail_tags = _strip_tag_tail(body)
    tags = [str(t).strip().lstrip("#")[:30] for t in (obj.get("tags") or []) if str(t).strip()][:10]
    for t in tail_tags:
        if t and t not in tags:
            tags.append(t)
    tags = tags[:10]
    hook = str(obj.get("hook") or "").strip()[:300]
    title = str(obj.get("title") or entry.title).strip()[:120]

    # 长度是硬约束：超了给明确提示，别让用户发出去才发现被截断
    over_limit = len(body) > spec["limit"]
    too_short = len(body) < spec["min_chars"]

    await _record(
        session,
        kind=_KIND_REDISTRIBUTE,
        target=f"entry:{entry.id}:{channel}",
        result=result,
        params={"channel": channel, "chars": len(body), "over_limit": over_limit},
        created_by=created_by,
        prompt=user_msg,
    )

    logger.info(
        f"[redistribute] entry={entry.id} channel={channel} chars={len(body)} over={over_limit}"
    )

    return {
        "entry_id": entry.id,
        "channel": channel,
        "channel_label": spec["label"],
        "title": title,
        "hook": hook,
        "body": body,
        "tags": tags,
        "notes": str(obj.get("notes") or "").strip()[:600],
        "chars": len(body),
        "limit": spec["limit"],
        "over_limit": over_limit,
        "too_short": too_short,
        # 渠道需要的成品文本，前端「复制全文」直接用这个，省得自己拼
        "full_text": _compose(title, hook, body, tags),
    }


def _strip_tag_tail(body: str) -> tuple[str, list[str]]:
    """剥掉正文末尾自带的话题标签行（模型常不听话，写两遍）。

    `tags` 是独立字段，前端会渲染成标签块、`_compose` 也会在 full_text
    末尾拼一次。模型若顺手把「#话题 #话题」写进 body 尾部，用户复制到的
    成品里标签就出现两次——看起来像系统拼接出了 bug。

    只剥**整行全部由 #标签 组成**的尾行，判断严格到不会误伤 Markdown 标题：
    `## 一、小标题` 的首 token 是 `##`（以 `#` 开头但不是标签），因此不满足
    全行都是标签，原样保留。
    """
    lines = body.rstrip().split("\n")
    found: list[str] = []
    while lines:
        tokens = lines[-1].strip().split()
        is_tag_line = bool(tokens) and all(
            t.startswith("#") and not t.startswith("##") and len(t) > 1 for t in tokens
        )
        if not is_tag_line:
            break
        # 前置拼接：尾行是从后往前剥的，直接 append 会让标签顺序倒过来
        found = [t.lstrip("#")[:30] for t in tokens] + found
        lines.pop()
    # 剥下来的标签若模型没填进 tags 字段，用来补齐（别白丢）
    return "\n".join(lines).rstrip(), found


def _compose(title: str, hook: str, body: str, tags: list[str]) -> str:
    parts = [title.strip()] if title.strip() else []
    if hook.strip() and not body.startswith(hook.strip()):
        parts.append(hook.strip())
    if body.strip():
        parts.append(body.strip())
    if tags:
        parts.append(" ".join(f"#{t}" for t in tags))
    return "\n\n".join(parts)


def channels_meta() -> list[dict[str, Any]]:
    return [
        {"key": k, "label": v["label"], "limit": v["limit"], "min_chars": v["min_chars"]}
        for k, v in CHANNELS.items()
    ]
