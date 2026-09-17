"""本体模块类型定义。

契约源：docs/20-本体服务接口规格.md v0.1-draft（对外独立服务接口）。
设计源：docs/13-本体与知识库深化设计.md §3.2（OntologyStore 数据模型）。
对外 DTO 一律经 to_payload() 平铺（不泄漏内部存储细节）；与契约测试/服务端共用。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def normalize_name(name: str) -> str:
    """实体名归一化：去空白、统一小写（merge key 的一部分）。"""
    return "".join(str(name or "").split()).lower()


def stable_id(*parts: str) -> str:
    """稳定 id：参与方归一化后 sha1 前 10 位——同名同类实体跨文档/重抽恒等（幂等 merge）。"""
    joined = "|".join(normalize_name(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:10]


@dataclass
class Entity:
    """业务实体（物料/检验单/角色/系统/流程节点/数据资产/合规要求…）。"""

    id: str
    type: str
    name: str
    properties: dict = field(default_factory=dict)
    confidence: float = 0.8
    source_docs: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""

    @classmethod
    def make_id(cls, etype: str, name: str) -> str:
        return stable_id(etype, name)

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "properties": self.properties,
            "confidence": self.confidence,
            "source_docs": self.source_docs,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


@dataclass
class Relation:
    """实体间关系（属于/触发/产生/依赖/消费/约束…）。from/to 为 Entity.id。"""

    from_entity: str
    to_entity: str
    relation_type: str
    source_docs: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "relation_type": self.relation_type,
            "source_docs": self.source_docs,
        }


@dataclass
class Rule:
    """业务规则（含合规红线）：IF condition THEN conclusion。"""

    id: str
    condition: str
    conclusion: str
    confidence: float = 0.8
    source_docs: list[str] = field(default_factory=list)

    @classmethod
    def make_id(cls, condition: str, conclusion: str) -> str:
        return stable_id(condition, conclusion)

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "condition": self.condition,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "source_docs": self.source_docs,
        }


@dataclass
class MergeReport:
    """一次 upsert_batch（通常对应一篇文档）的增量报告——"只增不重建"的观测面。"""

    doc_ref: str = ""
    entities_added: int = 0
    entities_merged: int = 0
    relations_added: int = 0
    rules_added: int = 0
    skipped_orphan_relations: int = 0
    skipped_deleted_entities: int = 0  # 人工删除（软删）不复活（13 号 §五 风险表）

    def to_payload(self) -> dict:
        return {
            "doc_ref": self.doc_ref,
            "entities_added": self.entities_added,
            "entities_merged": self.entities_merged,
            "relations_added": self.relations_added,
            "rules_added": self.rules_added,
            "skipped_orphan_relations": self.skipped_orphan_relations,
            "skipped_deleted_entities": self.skipped_deleted_entities,
        }


@dataclass
class OntologyGraph:
    """项目本体图（Dashboard Mermaid 直染 / 对外 /graph 载荷）。"""

    project_id: str
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)

    def to_payload(self) -> dict:
        active = [e for e in self.entities]
        by_type: dict[str, int] = {}
        for e in active:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        return {
            "project_id": self.project_id,
            "entities": [e.to_payload() for e in active],
            "relations": [r.to_payload() for r in self.relations],
            "rules": [r.to_payload() for r in self.rules],
            "stats": {
                "entities": len(active),
                "relations": len(self.relations),
                "rules": len(self.rules),
                "entity_types": by_type,
            },
        }


class OntologyError(Exception):
    """契约错误（对外服务/Remote 网关统一形态）。

    code 为稳定字符串码（对齐知识库契约 14 号 §4 的做法）：unauthorized /
    not_found / invalid_request / internal_error。
    """

    def __init__(self, code: str, message: str = "", http_status: int | None = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.http_status = http_status


class OntologyServiceError(Exception):
    """连接类故障（Remote 不可达/5xx）——Fallback 网关据此降级 Embedded。"""

    def __init__(self, message: str, *, degraded: bool = True):
        super().__init__(message)
        self.degraded = degraded
