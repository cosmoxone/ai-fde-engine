"""OntologyGateway 抽象 + Embedded/Remote/Fallback 实现 + 工厂。

三层形态镜像知识库接入层（src/knowledge/gateway.py）——本体同样可：
1. Embedded：进程内直连（默认，单机零依赖）；
2. Remote：ONTOLOGY_SERVICE_URL 配置即启用，消费独立部署的本体服务
   （对外接口契约：docs/20-本体服务接口规格.md）；
3. Fallback：Remote 故障（连接失败/5xx）自动降级 Embedded 并标记 degraded_since；
   契约错误（OntologyError：调用方 bug，如 404）不降级直接抛。

模块分离原则：ontology 不依赖 knowledge，反之亦然（pipeline 回填仅函数内 try-import）。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

import httpx

from ..config import get_settings
from .extractor import extract_ontology
from .store import EmbeddedOntologyStore
from .types import OntologyError, OntologyServiceError

logger = logging.getLogger(__name__)

_SEARCH_TIMEOUT = 10.0
_WRITE_TIMEOUT = 60.0


class OntologyGateway(Protocol):
    def health(self) -> dict: ...
    def stats(self, project_id: str) -> dict: ...
    async def extract_and_merge(
        self, project_id: str, title: str, content: str, doc_ref: str = "", industry: str = ""
    ) -> dict: ...
    def get_graph(self, project_id: str) -> dict: ...
    def get_mermaid(self, project_id: str) -> str: ...
    def get_summary(self, project_id: str) -> str: ...
    def find_entities(self, project_id: str, keyword: str, limit: int = 50) -> list[dict]: ...
    def delete_entity(self, project_id: str, entity_id: str) -> bool: ...
    def annotate_hints(self, project_id: str, content: str, title: str = "") -> list[str]: ...


def _get_llm():
    """有真实 LLM 配置才返回 client；否则 None（extractor 自动落 Mock）。"""
    try:
        from ..llm.client import get_llm_client

        client = get_llm_client()
        settings = get_settings()
        if not (settings.llm_api_key or "").strip():
            return None
        return client
    except Exception:  # noqa: BLE001
        return None


class EmbeddedOntologyGateway:
    """进程内参考实现（store + extractor）——契约 20 号行为基准。"""

    def __init__(self, db_path: str = ""):
        self._store = EmbeddedOntologyStore(db_path or self._default_db_path())

    @staticmethod
    def _default_db_path() -> str:
        import os

        settings = get_settings()
        if settings.ontology_db_path:
            return settings.ontology_db_path
        return os.path.join(settings.data_dir, "ontology.db")

    def health(self) -> dict:
        base = self._store.health()
        base["mode"] = "embedded"
        return base

    def stats(self, project_id: str) -> dict:
        return self._store.stats(project_id)

    async def extract_and_merge(
        self, project_id: str, title: str, content: str, doc_ref: str = "", industry: str = ""
    ) -> dict:
        entities, relations, rules, mode = await extract_ontology(title, content, llm=_get_llm())
        report = self._store.upsert_batch(project_id, entities, relations, rules, doc_ref=doc_ref)
        payload = report.to_payload()
        payload["mode"] = mode
        return payload

    def get_graph(self, project_id: str) -> dict:
        return self._store.get_graph(project_id).to_payload()

    def get_mermaid(self, project_id: str) -> str:
        return self._store.get_mermaid(project_id)

    def get_summary(self, project_id: str) -> str:
        return self._store.get_summary(project_id)

    def find_entities(self, project_id: str, keyword: str, limit: int = 50) -> list[dict]:
        return [e.to_payload() for e in self._store.find_entities(project_id, keyword, limit)]

    def delete_entity(self, project_id: str, entity_id: str) -> bool:
        return self._store.delete_entity(project_id, entity_id)

    def annotate_hints(self, project_id: str, content: str, title: str = "") -> list[str]:
        return self._store.annotate_hints(project_id, content, title)


class RemoteOntologyGateway:
    """HTTP 客户端（契约 20 号端点）；错误统一解包为 OntologyError/OntologyServiceError。"""

    def __init__(self, base_url: str, token: str = "", timeout: float = _WRITE_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(
            base_url=self.base_url, headers=self._headers, timeout=timeout, trust_env=False
        )  # 规避代理环境变量毒化（同 kbos.py）

    def _call(
        self,
        method: str,
        path: str,
        *,
        project: str | None = None,
        json_body: dict | None = None,
        timeout: float | None = None,
    ):
        headers = {"X-Onto-Project": project} if project else {}
        try:
            resp = self._http.request(method, path, json=json_body, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            raise OntologyServiceError(f"本体服务不可达: {exc}") from exc
        if resp.status_code >= 500:
            raise OntologyServiceError(f"本体服务 5xx: {resp.status_code}", degraded=True)
        if resp.status_code >= 400:
            err = {}
            try:
                err = (resp.json() or {}).get("error") or {}
            except ValueError:
                pass
            raise OntologyError(
                err.get("code", "invalid_request"),
                err.get("message", "") or resp.text[:200],
                http_status=resp.status_code,
            )
        return resp.json() if resp.content else {}

    def health(self) -> dict:
        return self._call("GET", "/health", timeout=_SEARCH_TIMEOUT)

    def stats(self, project_id: str) -> dict:
        return self._call("GET", "/stats", project=project_id, timeout=_SEARCH_TIMEOUT)

    async def extract_and_merge(
        self, project_id: str, title: str, content: str, doc_ref: str = "", industry: str = ""
    ) -> dict:
        return self._call(
            "POST",
            "/extract",
            project=project_id,
            json_body={"title": title, "content": content, "doc_ref": doc_ref, "industry": industry},
        )

    def get_graph(self, project_id: str) -> dict:
        return self._call("GET", "/graph", project=project_id, timeout=_SEARCH_TIMEOUT)

    def get_mermaid(self, project_id: str) -> str:
        headers = {"X-Onto-Project": project_id}
        try:
            resp = self._http.get("/mermaid", headers=headers, timeout=_SEARCH_TIMEOUT)
        except httpx.HTTPError as exc:
            raise OntologyServiceError(f"本体服务不可达: {exc}") from exc
        if resp.status_code >= 500:
            raise OntologyServiceError(f"本体服务 5xx: {resp.status_code}")
        if resp.status_code >= 400:
            raise OntologyError("invalid_request", resp.text[:200], resp.status_code)
        return resp.text

    def get_summary(self, project_id: str) -> str:
        return self._call("GET", "/summary", project=project_id, timeout=_SEARCH_TIMEOUT).get("summary", "")

    def find_entities(self, project_id: str, keyword: str, limit: int = 50) -> list[dict]:
        data = self._call("GET", "/entities", project=project_id, json_body=None, timeout=_SEARCH_TIMEOUT)
        return data.get("entities", [])[:limit]

    def delete_entity(self, project_id: str, entity_id: str) -> bool:
        return bool(self._call("DELETE", f"/entities/{entity_id}", project=project_id).get("deleted"))

    def annotate_hints(self, project_id: str, content: str, title: str = "") -> list[str]:
        data = self._call(
            "POST",
            "/hints",
            project=project_id,
            json_body={"content": content, "title": title},
            timeout=_SEARCH_TIMEOUT,
        )
        return data.get("hints", [])


class FallbackOntologyGateway:
    """Remote 优先 + Embedded 兜底（对齐知识库 Fallback 语义）。"""

    def __init__(self, remote: RemoteOntologyGateway, embedded: EmbeddedOntologyGateway):
        self._remote = remote
        self._embedded = embedded
        self.degraded_since: str | None = None

    def _call(self, method: str, *args, **kwargs) -> Any:
        try:
            result = getattr(self._remote, method)(*args, **kwargs)
            self.degraded_since = None
            return result
        except OntologyError:
            raise  # 调用方 bug：不降级
        except OntologyServiceError as exc:
            if self.degraded_since is None:
                logger.warning("本体 Remote 不可用，降级 Embedded: %s", exc)
            import datetime as _dt

            self.degraded_since = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
            return getattr(self._embedded, method)(*args, **kwargs)

    def health(self) -> dict:
        base = self._call("health")
        base["fallback"] = True
        base["degraded_since"] = self.degraded_since
        return base

    def stats(self, project_id: str) -> dict:
        return self._call("stats", project_id)

    async def extract_and_merge(
        self, project_id: str, title: str, content: str, doc_ref: str = "", industry: str = ""
    ) -> dict:
        return await self._call("extract_and_merge", project_id, title, content, doc_ref, industry)

    def get_graph(self, project_id: str) -> dict:
        return self._call("get_graph", project_id)

    def get_mermaid(self, project_id: str) -> str:
        return self._call("get_mermaid", project_id)

    def get_summary(self, project_id: str) -> str:
        return self._call("get_summary", project_id)

    def find_entities(self, project_id: str, keyword: str, limit: int = 50) -> list[dict]:
        return self._call("find_entities", project_id, keyword, limit)

    def delete_entity(self, project_id: str, entity_id: str) -> bool:
        return self._call("delete_entity", project_id, entity_id)

    def annotate_hints(self, project_id: str, content: str, title: str = "") -> list[str]:
        return self._call("annotate_hints", project_id, content, title)


_gateway: OntologyGateway | None = None
_gateway_lock = threading.Lock()


def get_ontology_gateway() -> OntologyGateway:
    """进程级单例：ONTOLOGY_SERVICE_URL 配置 → Remote(+Fallback)，否则 Embedded。"""
    global _gateway
    if _gateway is not None:
        return _gateway
    with _gateway_lock:
        if _gateway is None:
            settings = get_settings()
            if settings.ontology_service_url:
                remote = RemoteOntologyGateway(settings.ontology_service_url, settings.ontology_service_token)
                embedded = EmbeddedOntologyGateway()
                _gateway = FallbackOntologyGateway(remote, embedded)
            else:
                _gateway = EmbeddedOntologyGateway()
    return _gateway


def reset_ontology_gateway() -> None:
    """测试隔离用（conftest 逐测试重置）。"""
    global _gateway
    with _gateway_lock:
        _gateway = None
