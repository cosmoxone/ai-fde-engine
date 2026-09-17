"""KbOsGateway——走法 A 适配器：消费 kb-os 原生 API（Envelope + /api/v1/knowledge/*）。

依据：kb-os《09-ai-fde对接方案》v1.1 §四（字段映射 §4.4、错误码 §4.1.1、限流 §4.1）。

- 鉴权：Bearer 项目 scoped key（KNOWLEDGE_SERVICE_TOKEN）；key 即 kb-os 侧项目身份，
  engine 侧 project_id 不上线（多项目 key 注册表为 P2）
- 错误：error_key 优先（W1 起），数字码映射兜底；4xx → KBContractError（调用方 bug，不降级），
  连接失败 / service_degraded / 5xx → KnowledgeGatewayError（触发 Embedded 降级）
- 超时：search 5s / 写入 30s（规格 14 §6 联调约定）
"""

from __future__ import annotations

import httpx

from .types import DocSpec, EntrySpec, Hit, IngestReport, KBContractError, KnowledgeGatewayError, Source, Stats

NUM2STR = {
    0: "ok",
    40001: "invalid_request",
    40101: "unauthorized",
    40301: "scope_denied",
    40401: "not_found",
    42901: "quota_exceeded",
    50001: "internal_error",
    50002: "service_degraded",
    50003: "misconfigured",
}
_DEGRADED_CODES = {"service_degraded", "internal_error", "misconfigured"}


class KbOsGateway:
    """kb-os 原生 API 的 KnowledgeGateway 实现（模式 A，生产形态）"""

    def __init__(self, base_url: str, token: str = "", search_timeout: float = 5.0, write_timeout: float = 30.0):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=httpx.Timeout(search_timeout), trust_env=False
        )

    # ---------- 内部 ----------

    def _request(self, method: str, path: str, *, json=None, params=None, timeout: float | None = None) -> dict:
        try:
            resp = self._http.request(method, path, json=json, params=params, timeout=timeout or self._http.timeout)
        except httpx.HTTPError as exc:
            raise KnowledgeGatewayError(f"kb-os 连接失败: {exc}") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        code_num = body.get("code")
        if resp.status_code >= 400 or code_num not in (None, 0):
            code = body.get("error_key") or NUM2STR.get(code_num, f"unknown_{code_num}")
            message = body.get("message", "")
            if resp.status_code >= 500 or code in _DEGRADED_CODES:
                raise KnowledgeGatewayError(f"kb-os 降级态 [{code}] {message}", degraded=True)
            raise KBContractError(code, message, resp.status_code)
        return body.get("data") or {}

    @staticmethod
    def _hit_of(item: dict) -> Hit:
        meta = item.get("metadata") or {}
        return Hit(
            content=item.get("snippet", ""),
            source=Source(
                filename=meta.get("filename"),
                chunk_index=meta.get("chunk_index"),
                start_at=meta.get("start_at"),
                end_at=meta.get("end_at"),
                knowledge_id=meta.get("knowledge_id"),
            ),
            score=float(item.get("score", 0.0)),
            entry_type="curated" if meta.get("chunk_type") == "faq" else "chunk",
        )

    # ---------- 观测面 ----------

    def health(self) -> dict:
        try:
            resp = self._http.get("/health", timeout=5.0)
        except httpx.HTTPError as exc:
            raise KnowledgeGatewayError(f"kb-os 健康检查失败: {exc}") from exc
        data = resp.json() if resp.status_code < 400 else {}
        return {"status": data.get("status", "degraded"), "version": data.get("service")}

    def stats(self, project_id: str) -> Stats:  # key 即项目身份（scoped key，规格 §1）
        data = self._request("GET", "/api/v1/knowledge/stats")
        entries = data.get("entries") or {}
        return Stats(
            documents=int(data["documents"]),
            parsing=int(data["parsing"]),
            curated=int(entries.get("confirmed", 0)),
            pending=int(entries.get("pending", 0)),
            chunks=data.get("chunks"),
            parse_failed=data.get("parse_failed"),
            rejected=entries.get("rejected"),
        )

    # ---------- P0 ----------

    def ingest_documents(self, project_id: str, docs: list[DocSpec]) -> IngestReport:  # noqa: ARG002
        data = self._request(
            "POST",
            "/api/v1/knowledge/documents",
            timeout=30.0,
            json={"documents": [{"title": d.title, "content": d.content, "metadata": d.metadata} for d in docs]},
        )
        return IngestReport(int(data["accepted"]), int(data["deduped"]))

    def search(
        self,
        project_id: str,
        query: str,
        top_k: int = 5,  # noqa: ARG002
        entry_type: str = "any",
    ) -> list[Hit]:
        payload = {"query": query, "top_k": top_k}
        if entry_type in ("chunk", "curated"):
            payload["content_types"] = ["text", "summary"] if entry_type == "chunk" else ["faq"]
        data = self._request("POST", "/api/v1/knowledge/search", json=payload)
        return [self._hit_of(i) for i in data.get("items", [])]

    # ---------- P1 ----------

    def curate(self, project_id: str, entry: EntrySpec) -> tuple[str, str]:  # noqa: ARG002
        data = self._request("POST", "/api/v1/knowledge/entries", timeout=30.0, json=entry.to_payload())
        return data["entry_id"], data["status"]

    def list_pending(
        self,
        project_id: str,
        page: int = 1,  # noqa: ARG002
        page_size: int = 50,
    ) -> tuple[int, list[dict]]:
        data = self._request(
            "GET", "/api/v1/knowledge/entries", params={"status": "pending", "page": page, "page_size": page_size}
        )
        return int(data["total"]), list(data.get("entries", []))

    def confirm_entry(
        self,
        project_id: str,
        entry_id: str,  # noqa: ARG002
        edited: dict | None = None,
    ) -> str:
        data = self._request("POST", f"/api/v1/knowledge/entries/{entry_id}/confirm", timeout=30.0, json=edited or {})
        return data["status"]

    def reject_entry(
        self,
        project_id: str,
        entry_id: str,  # noqa: ARG002
        reason: str | None = None,
    ) -> str:
        data = self._request(
            "POST",
            f"/api/v1/knowledge/entries/{entry_id}/reject",
            timeout=30.0,
            json={"reason": reason} if reason else {},
        )
        return data["status"]

    def close(self) -> None:
        self._http.close()
