"""前期处理管线——引擎侧知识库挂钩（13 号 §3.1 职责②，v1.2 契约）。

职责：上传/批量导入后自动触发**文档级** ingest（切块主权归知识库侧，引擎只做
元数据预标注与整篇推送）；失败不阻断主流程，状态记入文档记录 `kb_status`。

entity_hints 预标注自 v0.4-b 起由本体抽取结果填充（当前留空，不违契约：存而不滤）。
"""

from __future__ import annotations

import logging

from .gateway import get_knowledge_gateway
from .types import DocSpec

logger = logging.getLogger("aifde.knowledge.pipeline")


def doc_record_to_spec(doc_record: dict, project_id: str = "") -> DocSpec:
    """引擎文档记录 → 契约 DocSpec（文档级主协议）"""
    structured = doc_record.get("structured") or []
    title_path = structured[0].get("title", "") if structured and isinstance(structured[0], dict) else ""
    return DocSpec(
        title=doc_record.get("filename") or doc_record.get("id") or "untitled",
        content=doc_record.get("content") or "",
        metadata={
            "doc_id": doc_record.get("id"),
            "title_path": title_path,
            "entity_hints": _annotate_entity_hints(project_id, doc_record),  # v0.4-b 本体预标注
            "origin": "fde-upload",
        },
    )


def _annotate_entity_hints(project_id: str, doc_record: dict) -> list[str]:
    """本体预标注（v0.4-b）：本体不可用/无数据 → 空（不违契约 14 号"存而不滤"）。

    函数内 try-import：知识库模块不硬依赖本体模块（模块分离，13 号 §二）。
    """
    if not project_id or not (doc_record.get("content") or "").strip():
        return []
    try:
        from ..ontology.service import annotate_hints  # noqa: PLC0415 —— 延迟绑定防循环

        return annotate_hints(project_id, doc_record.get("content") or "", doc_record.get("filename") or "")
    except Exception:  # noqa: BLE001 —— 预标注失败绝不阻断 ingest
        return []


def auto_ingest(project_id: str, doc_record: dict) -> str:
    """上传后自动入库；**永不抛异常**（知识库故障不得阻断上传），返回 kb_status。"""
    if doc_record.get("parse_status") != "parsed":
        return "skipped:not-parsed"
    if not (doc_record.get("content") or "").strip():
        return "skipped:empty-content"
    try:
        report = get_knowledge_gateway().ingest_documents(project_id, [doc_record_to_spec(doc_record)])
        return "ingested" if report.accepted else f"deduped:{report.deduped}"
    except Exception as exc:  # noqa: BLE001 —— 兜底一切知识库侧异常
        logger.warning("自动 ingest 失败（不阻断上传）: %s", exc)
        return f"failed:{type(exc).__name__}"


def rebuild_project_kb(project_id: str, doc_records: list[dict]) -> dict:
    """重建：全量重推项目已解析文档（幂等按 metadata.doc_id 去重）。"""
    specs = [
        doc_record_to_spec(d)
        for d in doc_records
        if d.get("parse_status") == "parsed" and (d.get("content") or "").strip()
    ]
    report = get_knowledge_gateway().ingest_documents(project_id, specs)
    return {"accepted": report.accepted, "deduped": report.deduped, "candidates": len(specs)}
