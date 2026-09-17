"""本体模块（v0.4-b，契约：docs/20-本体服务接口规格.md v0.1-draft）。

分层（镜像知识库接入层）：
- types/store：数据模型 + Embedded 参考实现（SQLite，增量 merge 幂等）
- extractor：LLM 结构化抽取 + Mock（行业模板派生，无 Key 流程可跑通）
- gateway：Embedded/Remote/Fallback + 工厂（ONTOLOGY_SERVICE_URL 配置即 Remote）
- service：任务化抽取编排 + entity_hints 预标注（知识库 pipeline 回填）
- server：对外独立 HTTP 服务（uvicorn src.ontology.server:app）

设计源：docs/13-本体与知识库深化设计.md §3.2（"本体留本项目"，业务建模层）。
"""

from .gateway import (
    EmbeddedOntologyGateway,
    FallbackOntologyGateway,
    RemoteOntologyGateway,
    get_ontology_gateway,
    reset_ontology_gateway,
)
from .types import (
    Entity,
    MergeReport,
    OntologyError,
    OntologyGraph,
    OntologyServiceError,
    Relation,
    Rule,
)

__all__ = [
    "Entity",
    "Relation",
    "Rule",
    "MergeReport",
    "OntologyGraph",
    "OntologyError",
    "OntologyServiceError",
    "EmbeddedOntologyGateway",
    "RemoteOntologyGateway",
    "FallbackOntologyGateway",
    "get_ontology_gateway",
    "reset_ontology_gateway",
]
