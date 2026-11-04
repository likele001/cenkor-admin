"""开发者文档 API —— 在后台直接看开发文档，并一键灌入知识库。

模板开发者最常见的三个问题：
1. 「theme.json 怎么写？」→ 文档页直接查
2. 「这个过滤器叫什么？」→ 文档页搜
3. 「AI 能不能帮我写模板？」→ 把文档灌进知识库，AI 有据可依

所以文档不是「发布后就没人看的 PDF」，而是**开发工具链的一部分**。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from cenkor_admin.api.deps import get_current_user, require_permission
from cenkor_admin.apps.auth import models as auth_models
from cenkor_admin.core.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

# 文档根目录：从包内向上找到仓库根，再进 docs/
_DOCS_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent / "docs"

# 允许后台展示的文档（白名单，避免暴露内部文档）
_DOC_WHITELIST = {
    "template-guide.md": "模板开发指南",
    "theme-market.md": "模板市场指南",
    "dev_guide.md": "开发者指南",
    "core_platform.md": "核心平台架构",
    "cms-ai.md": "AI 能力说明",
    "database-migrations.md": "数据库迁移",
    "packaging.md": "打包与分发",
    "deploy.md": "部署指南",
    "mcp.md": "MCP 协议",
}


def _list_docs() -> list[dict[str, Any]]:
    """列出白名单内的文档。"""
    out = []
    for filename, title in _DOC_WHITELIST.items():
        path = _DOCS_ROOT / filename
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        # 提取第一行作为摘要
        first_line = content.split("\n", 1)[0].lstrip("# ").strip()
        out.append({
            "id": filename.replace(".md", ""),
            "filename": filename,
            "title": title,
            "summary": first_line[:200],
            "size": len(content),
            "updated_at": path.stat().st_mtime,
        })
    return out


@router.get("/developer/docs")
async def list_developer_docs(
    _: auth_models.User = Depends(get_current_user),
):
    """列出开发者文档（白名单内的 docs/*.md）。"""
    return {"items": _list_docs()}


@router.get("/developer/docs/{doc_id}")
async def get_developer_doc(
    doc_id: str,
    _: auth_models.User = Depends(get_current_user),
):
    """获取单个文档的 Markdown 内容。"""
    filename = f"{doc_id}.md"
    if filename not in _DOC_WHITELIST:
        raise HTTPException(404, f"文档不存在：{doc_id}")

    path = _DOCS_ROOT / filename
    if not path.exists():
        raise HTTPException(404, f"文档文件不存在：{filename}")

    content = path.read_text(encoding="utf-8")
    return {
        "id": doc_id,
        "filename": filename,
        "title": _DOC_WHITELIST[filename],
        "content": content,
    }


@router.post("/developer/docs/import-kb")
async def import_docs_to_kb(
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    user: auth_models.User = Depends(require_permission("cms:ai:write")),
):
    """把开发文档灌入知识库（异步索引）。

    灌完之后 AI 就能回答「theme.json 怎么写」这类问题了。
    重复灌入不会产生重复文档（内容完全一致时跳过）。
    """
    from cenkor_admin.apps.cms import knowledge

    site_id = int((body or {}).get("site_id") or 1)
    doc_ids = (body or {}).get("doc_ids") or list(_DOC_WHITELIST.keys())

    imported, skipped, errors = [], [], []
    for filename in doc_ids:
        if filename not in _DOC_WHITELIST:
            errors.append(f"未知文档：{filename}")
            continue

        path = _DOCS_ROOT / filename
        if not path.exists():
            errors.append(f"文档文件不存在：{filename}")
            continue

        content = path.read_text(encoding="utf-8")
        title = _DOC_WHITELIST[filename]

        try:
            _doc, created = await knowledge.create_doc(
                db,
                title=f"[开发文档] {title}",
                content=content,
                source_type="paste",
                category="开发文档",
                note=f"从 docs/{filename} 同步",
                created_by=getattr(user, "id", None),
                site_id=site_id,
            )
            if created:
                imported.append(filename)
            else:
                skipped.append(filename)
        except Exception as exc:
            logger.warning("developer_docs.import_failed", doc=filename, error=str(exc))
            errors.append(f"{filename}: {exc}")

    await db.commit()

    return {
        "ok": not errors,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total": len(doc_ids),
    }
