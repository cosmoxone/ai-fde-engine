"""kbos 断言适配:消费 kb-os 原生 API(Envelope 信封 + /api/v1/knowledge/*)。

依据:kb-os《09-ai-fde对接方案》v1.1 §四(字段映射 §4.4、错误码 §4.1.1)。
该适配即 KbOsGateway 的测试同构(生产适配器见 src/knowledge/,v0.4-a 交付)。
"""

from __future__ import annotations

import httpx

from .core import (
    DocSpec,
    EntrySpec,
    Expectations,
    Hit,
    KBClient,
    KBError,
    Source,
    Stats,
)

# kb-os 数字码 → 规格字符串码(09 方案 §4.1.1 ↔ 规格 14 §4;error_key 缺省时兜底)
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


class KbOsClient(KBClient):
    profile = "kbos"
    expectations = Expectations(over_limit=frozenset({"invalid_request"}))

    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=timeout, trust_env=False)

    # ---------- 内部 ----------

    def _unwrap(self, resp: httpx.Response) -> dict:
        """Envelope 解包:code!=0 或 HTTP>=400 → KBError(error_key 优先,数字映射兜底)"""
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 - 非 JSON 响应按 HTTP 状态归一
            body = {}
        code_num = body.get("code")
        error_key = body.get("error_key") or ""
        if resp.status_code >= 400 or code_num not in (None, 0):
            code = error_key or NUM2STR.get(code_num, f"unknown_{code_num}")
            raise KBError(resp.status_code, code, body.get("message", ""))
        return body.get("data") or {}

    def _call(self, method: str, path: str, *, json=None, params=None) -> dict:
        resp = self._http.request(method, path, json=json, params=params)
        return self._unwrap(resp)

    @staticmethod
    def _doc_payload(doc: DocSpec) -> dict:
        return {"title": doc.title, "content": doc.content, "metadata": doc.metadata}

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
            # chunk_type: text|summary|faq;faq 即 curated(09 方案 §4.4)
            entry_type="curated" if meta.get("chunk_type") == "faq" else "chunk",
        )

    # ---------- 观测面 ----------

    def health(self) -> dict:
        # /health 不走 Envelope(09 方案 §4.1:{"status","service","audit_pg"})
        resp = self._http.get("/health")
        if resp.status_code >= 400:
            raise KBError(resp.status_code, "unknown", "health check failed")
        data = resp.json()
        return {"status": data.get("status"), "version": data.get("service")}

    def stats(self) -> Stats:
        data = self._call("GET", "/api/v1/knowledge/stats")
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

    def ingest_documents(self, docs: list[DocSpec]) -> tuple[int, int]:
        data = self._call(
            "POST", "/api/v1/knowledge/documents", json={"documents": [self._doc_payload(d) for d in docs]}
        )
        return int(data["accepted"]), int(data["deduped"])

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        data = self._call("POST", "/api/v1/knowledge/search", json={"query": query, "top_k": top_k})
        return [self._hit_of(i) for i in data.get("items", [])]

    # ---------- P1 ----------

    def curate(self, entry: EntrySpec) -> tuple[str, str]:
        data = self._call("POST", "/api/v1/knowledge/entries", json=entry.to_payload())
        return data["entry_id"], data["status"]

    def list_pending(self, page: int = 1, page_size: int = 50) -> tuple[int, list[dict]]:
        data = self._call(
            "GET", "/api/v1/knowledge/entries", params={"status": "pending", "page": page, "page_size": page_size}
        )
        return int(data["total"]), list(data.get("entries", []))

    def confirm(self, entry_id: str, edited: dict | None = None) -> str:
        data = self._call("POST", f"/api/v1/knowledge/entries/{entry_id}/confirm", json=edited or {})
        return data["status"]

    def reject(self, entry_id: str, reason: str | None = None) -> str:
        data = self._call(
            "POST", f"/api/v1/knowledge/entries/{entry_id}/reject", json={"reason": reason} if reason else {}
        )
        return data["status"]

    # ---------- 错误分支触发器 ----------

    def trigger_invalid_request(self) -> None:
        self._call("POST", "/api/v1/knowledge/search", json={"top_k": 5})  # 缺 query → 40001

    def trigger_over_limit(self) -> None:
        from .core import make_doc, marker_token

        marker = marker_token()
        docs = [make_doc(marker, i) for i in range(51)]  # 单批上限 50(09 方案 §4.3.1)
        self._call("POST", "/api/v1/knowledge/documents", json={"documents": [self._doc_payload(d) for d in docs]})

    def probe_no_auth(self) -> tuple[int, str | None]:
        with httpx.Client(base_url=str(self._http.base_url), timeout=10.0, trust_env=False) as bare:
            resp = bare.get("/api/v1/knowledge/bases")
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                return resp.status_code, None
            code = body.get("error_key") or NUM2STR.get(body.get("code"))
            return resp.status_code, code

    def close(self) -> None:
        self._http.close()
