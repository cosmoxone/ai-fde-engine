"""知识库接入层（v0.4-a，契约：docs/14-知识库接口规格.md v1.2）。

职责（设计见 docs/13-本体与知识库深化设计.md §3.1）：
- KnowledgeGateway 抽象 + 工厂（gateway.py）：Embedded（零依赖默认）/ KbOs（走法 A）/ Fallback 降级
- EmbeddedKnowledgeGateway（embedded.py）：SQLite FTS5 参考实现——「参考实现即规格」
- KbOsGateway（kbos.py）：kb-os 原生 API 适配器（09-ai-fde对接方案 §4.4 映射表）
- chunker（chunker.py）：标题感知切块器（Embedded 内部 + 附录 A 降级模式）
- server（server.py）：spec14 HTTP 参考服务（契约测试双跑 / 进程外访问）
"""

from .embedded import EmbeddedKnowledgeGateway
from .gateway import FallbackKnowledgeGateway, get_knowledge_gateway, reset_knowledge_gateway
from .kbos import KbOsGateway
from .types import DocSpec, EntrySpec, Hit, IngestReport, KBContractError, KnowledgeGatewayError, Source, Stats

__all__ = [
    "EmbeddedKnowledgeGateway",
    "KbOsGateway",
    "FallbackKnowledgeGateway",
    "get_knowledge_gateway",
    "reset_knowledge_gateway",
    "DocSpec",
    "EntrySpec",
    "Hit",
    "IngestReport",
    "Source",
    "Stats",
    "KBContractError",
    "KnowledgeGatewayError",
]
