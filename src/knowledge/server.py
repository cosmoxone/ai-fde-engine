"""spec14 参考服务——把任意 KnowledgeGateway 以规格 14 v1.2 HTTP 契约暴露。

用途：
1. 契约测试双跑（tests/contract，KB_PROFILE=spec14 指向本服务）：
   `uvicorn src.knowledge.server:app --port 9000`
2. 单机零依赖形态下的进程外访问（可选；默认 Embedded 直接进程内调用）

鉴权：配置 KNOWLEDGE_SERVICE_TOKEN 后强制 Bearer（401 unauthorized，规格 §4）；
项目上下文：X-KB-Project 头（默认 "default"）——参考服务为单 key/多项目演示形态，
生产多租户由 kb-os scoped key 承担（规格 v1.2 §1）。

错误响应统一 {"error": {"code", "message"}}（规格 §4）；附录 A 降级模式一并暴露。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .gateway import get_knowledge_gateway
from .types import DocSpec, EntrySpec, KBContractError

_MAX_DOCS_PER_BATCH = 50  # 规格 §3.1
_MAX_CHUNKS_PER_BATCH = 500  # 规格 附录A


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(gateway=None, token: str = "") -> FastAPI:
    app = FastAPI(title="AI-FDE Knowledge Service (spec14 reference)", version="0.4.0", docs_url="/docs")
    _token = token or os.environ.get("KNOWLEDGE_SERVICE_TOKEN", "")
    _gateway = gateway or get_knowledge_gateway()

    @app.exception_handler(KBContractError)
    async def _contract_error(_req: Request, exc: KBContractError):
        return _error_response(exc.http_status or 400, exc.code, exc.message)

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if _token:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {_token}":
                return _error_response(401, "unauthorized", "凭证缺失或无效（规格 §4）")
        return await call_next(request)

    def _project(request: Request) -> str:
        return request.headers.get("X-KB-Project", "default")

    @app.get("/health")
    async def health():
        data = _gateway.health()
        return {"status": data.get("status", "ok"), "version": data.get("version", "0.4.0")}

    @app.post("/ingest")
    async def ingest(body: dict, request: Request):
        documents = body.get("documents")
        if (
            not isinstance(documents, list)
            or not documents
            or not all(isinstance(d, dict) and d.get("title") and d.get("content") is not None for d in documents)
        ):
            return _error_response(400, "invalid_request", "documents: [{title, content, metadata}] 必填（规格 §3.1）")
        if len(documents) > _MAX_DOCS_PER_BATCH:
            return _error_response(413, "payload_too_large", f"单批上限 {_MAX_DOCS_PER_BATCH} 篇（规格 §3.1）")
        report = _gateway.ingest_documents(
            _project(request),
            [DocSpec(title=d["title"], content=d["content"], metadata=d.get("metadata") or {}) for d in documents],
        )
        return {"accepted": report.accepted, "deduped": report.deduped}

    @app.post("/ingest/chunks")
    async def ingest_chunks(body: dict, request: Request):
        chunks = body.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            return _error_response(400, "invalid_request", "chunks 必填（规格 附录A）")
        if len(chunks) > _MAX_CHUNKS_PER_BATCH:
            return _error_response(413, "payload_too_large", f"单批上限 {_MAX_CHUNKS_PER_BATCH} 块（规格 附录A）")
        report = _gateway.ingest_chunks(_project(request), chunks)
        return {"accepted": report.accepted, "deduped": report.deduped}

    @app.post("/search")
    async def search(body: dict, request: Request):
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            return _error_response(400, "invalid_request", "query 必填（规格 §3.2）")
        top_k = body.get("top_k", 5)
        entry_type = (body.get("filter") or {}).get("entry_type", "any")
        hits = _gateway.search(_project(request), query, top_k=int(top_k), entry_type=entry_type)
        return {
            "hits": [
                {
                    "content": h.content,
                    "source": {
                        "filename": h.source.filename,
                        "chunk_index": h.source.chunk_index,
                        "start_at": h.source.start_at,
                        "end_at": h.source.end_at,
                        "knowledge_id": h.source.knowledge_id,
                    },
                    "score": round(h.score, 4),
                    "entry_type": h.entry_type,
                }
                for h in hits
            ]
        }

    @app.post("/curate")
    async def curate(body: dict, request: Request):
        entry = body.get("entry")
        if not isinstance(entry, dict) or not entry.get("question_pattern") or not entry.get("answer"):
            return _error_response(400, "invalid_request", "entry: {question_pattern, answer} 必填（规格 §3.3）")
        entry_id, status = _gateway.curate(
            _project(request),
            EntrySpec(
                question_pattern=entry["question_pattern"],
                answer=entry["answer"],
                origin=entry.get("origin"),
                suggested_by=entry.get("suggested_by"),
                similar_questions=entry.get("similar_questions"),
            ),
        )
        return {"entry_id": entry_id, "status": status}

    @app.get("/pending")
    async def pending(request: Request, page: int = 1, page_size: int = 50):
        total, entries = _gateway.list_pending(_project(request), page=page, page_size=page_size)
        return {"total": total, "page": page, "page_size": page_size, "entries": entries}

    @app.post("/entries/{entry_id}/confirm")
    async def confirm(entry_id: str, body: dict | None = None, request: Request = None):
        edited = None
        if isinstance(body, dict) and (body.get("answer") or body.get("question_pattern")):
            edited = body
        status = _gateway.confirm_entry(_project(request), entry_id, edited=edited)
        return {"entry_id": entry_id, "status": status}

    @app.post("/entries/{entry_id}/reject")
    async def reject(entry_id: str, body: dict | None = None, request: Request = None):
        status = _gateway.reject_entry(_project(request), entry_id, reason=(body or {}).get("reason"))
        return {"entry_id": entry_id, "status": status}

    @app.get("/stats")
    async def stats(request: Request):
        s = _gateway.stats(_project(request))
        payload = {"documents": s.documents, "parsing": s.parsing, "curated": s.curated, "pending": s.pending}
        for key in ("chunks", "parse_failed", "rejected"):
            value = getattr(s, key)
            if value is not None:
                payload[key] = value
        return payload

    @app.get("/documents/{knowledge_id}")
    async def get_document(knowledge_id: str, request: Request):
        return _gateway.get_document(_project(request), knowledge_id)

    return app


app = create_app()
