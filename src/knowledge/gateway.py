"""KnowledgeGateway——知识库接入抽象与工厂（设计见 13 号 §3.1，规格 14 v1.2）。

实现体系：
- EmbeddedKnowledgeGateway（embedded.py）：进程内参考实现，零依赖默认（模式 B）
- KbOsGateway（kbos.py）：kb-os 原生 API 适配器（模式 A / 走法 A）
- FallbackKnowledgeGateway（本模块）：Remote 优先 + Embedded 兜底包装

工厂策略（get_knowledge_gateway）：
- 配置 KNOWLEDGE_SERVICE_URL → KbOs + Fallback 包装（Remote 不可用自动降级 Embedded，
  标记数据延迟，不阻断主流程——规格 14 §6）
- 未配置 → Embedded（单机开箱即用）

Embedded 模式无 HTTP 鉴权：project_id 由 Gateway 抽象内部隔离（规格 v1.2 §1）。
"""

from __future__ import annotations

import logging
import threading
import time

from src.config import get_settings

from .embedded import EmbeddedKnowledgeGateway
from .kbos import KbOsGateway
from .types import KnowledgeGatewayError

logger = logging.getLogger("aifde.knowledge")

# Fallback 包装需代理的方法集（契约客户端面）
_METHODS = (
    "health",
    "stats",
    "ingest_documents",
    "ingest_chunks",
    "search",
    "curate",
    "list_pending",
    "confirm_entry",
    "reject_entry",
    "get_document",
)


class FallbackKnowledgeGateway:
    """Remote 优先 + Embedded 兜底（规格 §6 连接语义的落地）。

    - KBContractError（4xx 调用方 bug）：直接抛出，不降级
    - KnowledgeGatewayError（连接失败 / service_degraded）：降级 Embedded 并标记
      degraded_since（Dashboard 状态页展示"数据延迟"）
    """

    def __init__(self, remote: KbOsGateway, embedded: EmbeddedKnowledgeGateway):
        self._remote = remote
        self._embedded = embedded
        self.degraded_since: float | None = None

    def _call(self, method: str, *args, **kwargs):
        target = self._remote if self.degraded_since is None else self._embedded
        try:
            return getattr(target, method)(*args, **kwargs)
        except KnowledgeGatewayError as exc:
            if self.degraded_since is None:
                logger.warning("知识库 Remote 不可用，降级 Embedded: %s", exc)
                self.degraded_since = time.time()
            return getattr(self._embedded, method)(*args, **kwargs)

    def retry_remote(self) -> bool:
        """尝试恢复 Remote（降级期间周期调用；成功则清除降级标记）"""
        try:
            if self._remote.health().get("status") == "ok":
                self.degraded_since = None
                return True
        except KnowledgeGatewayError:
            pass
        return False

    def __getattr__(self, name: str):
        if name in _METHODS:
            return lambda *a, **kw: self._call(name, *a, **kw)
        raise AttributeError(name)

    def close(self) -> None:
        self._remote.close()
        self._embedded.close()


_gateway_lock = threading.Lock()
_gateway_instance = None


def get_knowledge_gateway():
    """按配置返回网关（进程级单例；测试用 reset_knowledge_gateway 重置）"""
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is not None:
            return _gateway_instance
        settings = get_settings()
        if settings.knowledge_service_url:
            remote = KbOsGateway(settings.knowledge_service_url, token=settings.knowledge_service_token)
            embedded = EmbeddedKnowledgeGateway(settings.knowledge_db_path or "")
            _gateway_instance = FallbackKnowledgeGateway(remote, embedded)
        else:
            _gateway_instance = EmbeddedKnowledgeGateway(settings.knowledge_db_path or "")
        return _gateway_instance


def reset_knowledge_gateway() -> None:
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is not None:
            _gateway_instance.close()
        _gateway_instance = None
