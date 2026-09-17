"""本体应用服务：任务化抽取编排 + engine 侧胶水。

- extract_for_documents：POST /ontology/extract 的实现体——按 doc_ref 记账增量
  （已抽取文档默认跳过，force=True 重抽；store merge 幂等保证图规模不重复增长）；
- annotate_hints：知识库 ingest 的 entity_hints 预标注入口（pipeline 函数内 try-import
  调用，本体不可用回退空列表——不违知识库契约 14 号"存而不滤"）。
"""

from __future__ import annotations

import logging

from .gateway import get_ontology_gateway
from .store import EmbeddedOntologyStore

logger = logging.getLogger(__name__)


def _inner_store(gateway):
    inner = getattr(gateway, "_embedded", None) or gateway
    store = getattr(inner, "_store", None)
    return store if isinstance(store, EmbeddedOntologyStore) else None


async def extract_for_documents(
    project_id: str, doc_records: list[dict], doc_ids: list[str] | None = None, force: bool = False
) -> dict:
    """对项目已解析文档做增量本体抽取。

    doc_ids 指定子集；None = 全部 parse_status=parsed 且有内容的文档。
    返回汇总报告（每篇文档一行 MergeReport + 总计）。
    """
    gateway = get_ontology_gateway()
    store = _inner_store(gateway)

    candidates = []
    for d in doc_records:
        if d.get("parse_status") != "parsed":
            continue
        if not (d.get("content") or "").strip():
            continue
        if doc_ids is not None and d.get("id") not in doc_ids:
            continue
        candidates.append(d)

    reports: list[dict] = []
    skipped = 0
    for d in candidates:
        doc_ref = str(d.get("id") or d.get("filename") or "")
        if (not force) and store is not None and store.is_extracted(project_id, doc_ref):
            skipped += 1
            continue
        try:
            report = await gateway.extract_and_merge(
                project_id,
                title=str(d.get("filename") or d.get("id") or "untitled"),
                content=d.get("content") or "",
                doc_ref=doc_ref,
                industry=str(d.get("industry") or ""),
            )
            reports.append(report)
        except Exception as exc:  # noqa: BLE001 —— 单篇失败不阻断批次
            logger.warning("本体抽取失败 doc=%s: %s", doc_ref, exc)
            reports.append({"doc_ref": doc_ref, "error": type(exc).__name__})

    totals = {
        "entities_added": sum(r.get("entities_added", 0) for r in reports),
        "entities_merged": sum(r.get("entities_merged", 0) for r in reports),
        "relations_added": sum(r.get("relations_added", 0) for r in reports),
        "rules_added": sum(r.get("rules_added", 0) for r in reports),
    }
    return {
        "project_id": project_id,
        "extracted": len(reports),
        "skipped_already_extracted": skipped,
        "docs": reports,
        "totals": totals,
        "stats": gateway.stats(project_id),
    }


def annotate_hints(project_id: str, content: str, title: str = "") -> list[str]:
    """entity_hints 预标注（知识库 pipeline 回填入口；任何异常由调用方兜底为空）。"""
    return get_ontology_gateway().annotate_hints(project_id, content, title)
