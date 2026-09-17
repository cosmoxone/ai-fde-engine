"""spec14 断言适配:消费《14-知识库接口规格 v1.2》平铺契约的实现。

适用:Embedded 参考实现(v0.4-a 起)、任何 spec 兼容的第三方知识库服务。
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


class Spec14Client(KBClient):
    profile = "spec14"
    expectations = Expectations(over_limit=frozenset({"payload_too_large"}))

    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=timeout, trust_env=False)

    # ---------- 内部 ----------

    def _call(
        self, method: str, path: str, *, json=None, params=None, http: httpx.Client | None = None
    ) -> httpx.Response:
        client = http or self._http
        resp = client.request(method, path, json=json, params=params)
        if resp.status_code >= 400:
            code, message = "unknown", ""
            try:
                body = resp.json().get("error", {})
                code, message = body.get("code", "unknown"), body.get("message", "")
            except Exception:  # noqa: BLE001 - 非 JSON 错误体只保留 HTTP 状态
                pass
            raise KBError(resp.status_code, code, message)
        return resp

    def _error_code_of(self, resp: httpx.Response) -> str | None:
        try:
            return resp.json().get("error", {}).get("code")
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _doc_payload(doc: DocSpec) -> dict:
        return {"title": doc.title, "content": doc.content, "metadata": doc.metadata}

    @staticmethod
    def _hit_of(h: dict) -> Hit:
        s = h.get("source") or {}
        return Hit(
            content=h["content"],
            source=Source(
                filename=s.get("filename"),
                chunk_index=s.get("chunk_index"),
                start_at=s.get("start_at"),
                end_at=s.get("end_at"),
                knowledge_id=s.get("knowledge_id"),
            ),
            score=float(h.get("score", 0.0)),
            entry_type=h.get("entry_type", "chunk"),
        )

    # ---------- 观测面 ----------

    def health(self) -> dict:
        return self._call("GET", "/health").json()

    def stats(self) -> Stats:
        data = self._call("GET", "/stats").json()
        return Stats(
            documents=int(data["documents"]),
            parsing=int(data["parsing"]),
            curated=int(data["curated"]),
            pending=int(data["pending"]),
            chunks=data.get("chunks"),
            parse_failed=data.get("parse_failed"),
            rejected=data.get("rejected"),
        )

    # ---------- P0 ----------

    def ingest_documents(self, docs: list[DocSpec]) -> tuple[int, int]:
        data = self._call("POST", "/ingest", json={"documents": [self._doc_payload(d) for d in docs]}).json()
        return int(data["accepted"]), int(data["deduped"])

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        data = self._call("POST", "/search", json={"query": query, "top_k": top_k}).json()
        return [self._hit_of(h) for h in data.get("hits", [])]

    # ---------- P1 ----------

    def curate(self, entry: EntrySpec) -> tuple[str, str]:
        data = self._call("POST", "/curate", json={"entry": entry.to_payload()}).json()
        return data["entry_id"], data["status"]

    def list_pending(self, page: int = 1, page_size: int = 50) -> tuple[int, list[dict]]:
        data = self._call("GET", "/pending", params={"page": page, "page_size": page_size}).json()
        return int(data["total"]), list(data.get("entries", []))

    def confirm(self, entry_id: str, edited: dict | None = None) -> str:
        data = self._call("POST", f"/entries/{entry_id}/confirm", json=edited or {}).json()
        return data["status"]

    def reject(self, entry_id: str, reason: str | None = None) -> str:
        data = self._call("POST", f"/entries/{entry_id}/reject", json={"reason": reason} if reason else {}).json()
        return data["status"]

    # ---------- 错误分支触发器 ----------

    def trigger_invalid_request(self) -> None:
        self._call("POST", "/search", json={"top_k": 5})  # 缺 query

    def trigger_over_limit(self) -> None:
        from .core import make_doc, marker_token

        marker = marker_token()
        docs = [make_doc(marker, i) for i in range(51)]  # 单批上限 50(规格 §3.1)
        self._call("POST", "/ingest", json={"documents": [self._doc_payload(d) for d in docs]})

    def probe_no_auth(self) -> tuple[int, str | None]:
        with httpx.Client(base_url=str(self._http.base_url), timeout=10.0, trust_env=False) as bare:
            resp = bare.get("/stats")
            return resp.status_code, self._error_code_of(resp)

    def close(self) -> None:
        self._http.close()
