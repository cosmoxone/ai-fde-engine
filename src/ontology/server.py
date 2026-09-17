"""本体独立服务（对外 HTTP 契约：docs/20-本体服务接口规格.md v0.1-draft）。

用途（响应对外独立服务/独立组件融合需求）：
1. 本体能力独立部署：`uvicorn src.ontology.server:app --port 8020`
   其他组件（或主引擎 Remote 模式）经此消费本体抽取/图/摘要/预标注；
2. 契约行为参考实现（EmbeddedOntologyGateway 即规格）。

鉴权：配置 ONTOLOGY_SERVICE_TOKEN 后强制 Bearer（401 unauthorized）；
项目上下文：X-Onto-Project 头（默认 "default"）——单 token/多项目演示形态，
生产多租户可换独立部署侧的 scoped key（对齐知识库 14 号 v1.2 §1 演进路径）。
错误统一 {"error": {"code", "message"}}。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

from .gateway import EmbeddedOntologyGateway
from .types import OntologyError


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


class ExtractBody(BaseModel):
    title: str = ""
    content: str
    doc_ref: str = ""
    industry: str = ""


class HintsBody(BaseModel):
    title: str = ""
    content: str = ""


def create_app(gateway: EmbeddedOntologyGateway | None = None, token: str | None = None) -> FastAPI:
    gw = gateway or EmbeddedOntologyGateway()
    auth_token = token if token is not None else os.environ.get("ONTOLOGY_SERVICE_TOKEN", "")
    app = FastAPI(title="AI-FDE Ontology Service", version="0.4.0", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if auth_token and request.url.path != "/health":
            header = request.headers.get("Authorization", "")
            if header != f"Bearer {auth_token}":
                return _error(401, "unauthorized", "缺少或无效的 Bearer token")
        return await call_next(request)

    def _project(request: Request) -> str:
        return request.headers.get("X-Onto-Project") or "default"

    @app.exception_handler(OntologyError)
    async def _ontology_error(_: Request, exc: OntologyError):
        return _error(exc.http_status or 400, exc.code, exc.message)

    @app.get("/health")
    async def health():
        return gw.health()

    @app.post("/extract")
    async def extract(body: ExtractBody, request: Request):
        if not (body.content or "").strip():
            return _error(400, "invalid_request", "content 不能为空")
        if len(body.content) > 1_000_000:
            return _error(413, "payload_too_large", "content 超 1MB 上限")
        return await gw.extract_and_merge(
            _project(request), body.title, body.content, doc_ref=body.doc_ref, industry=body.industry
        )

    @app.get("/graph")
    async def graph(request: Request):
        return gw.get_graph(_project(request))

    @app.get("/mermaid")
    async def mermaid(request: Request):
        return PlainTextResponse(gw.get_mermaid(_project(request)))

    @app.get("/summary")
    async def summary(request: Request):
        return {"summary": gw.get_summary(_project(request))}

    @app.get("/stats")
    async def stats(request: Request):
        return gw.stats(_project(request))

    @app.get("/entities")
    async def entities(request: Request, q: str = "", limit: int = 50):
        items = gw.find_entities(_project(request), q, limit=limit)
        return {"entities": items, "total": len(items)}

    @app.delete("/entities/{entity_id}")
    async def delete_entity(entity_id: str, request: Request):
        if not gw.delete_entity(_project(request), entity_id):
            return _error(404, "not_found", f"实体不存在或已删除: {entity_id}")
        return {"deleted": True, "id": entity_id}

    @app.post("/hints")
    async def hints(body: HintsBody, request: Request):
        """entity_hints 预标注（前期处理组件融合入口；知识库 ingest metadata 用）。"""
        return {"hints": gw.annotate_hints(_project(request), body.content, body.title)}

    return app


app = create_app()
