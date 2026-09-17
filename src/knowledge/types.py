"""知识库接入层类型定义（v0.4-a）。

契约源：docs/14-知识库接口规格.md v1.2（通用契约，Embedded 参考实现即规格）。
注意：tests/contract/core.py 有一份同构拷贝（契约测试需可独立分发 kb-os，勿互相 import）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DocSpec:
    """文档级推送单元（主协议，规格 §3.1）"""

    title: str
    content: str
    metadata: dict


@dataclass
class EntrySpec:
    """知识条目草稿（规格 §3.3）"""

    question_pattern: str
    answer: str
    origin: str | None = None
    suggested_by: str | None = None
    similar_questions: list[str] | None = None

    def to_payload(self) -> dict:
        payload = {"question_pattern": self.question_pattern, "answer": self.answer}
        for key in ("origin", "suggested_by", "similar_questions"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload


@dataclass
class Source:
    """溯源五字段（规格 §3.2 必填）"""

    filename: str | None = None
    chunk_index: int | None = None
    start_at: int | None = None
    end_at: int | None = None
    knowledge_id: str | None = None


@dataclass
class Hit:
    content: str
    source: Source
    score: float
    entry_type: str  # chunk | curated


@dataclass
class Stats:
    """统计口径（规格 §3.6）：三元不变量 documents+parsing(+parse_failed)=累计接受"""

    documents: int
    parsing: int
    curated: int
    pending: int
    chunks: int | None = None
    parse_failed: int | None = None
    rejected: int | None = None


@dataclass
class IngestReport:
    accepted: int
    deduped: int


class KBContractError(Exception):
    """契约级错误（4xx 业务错误）——携带稳定字符串码（规格 §4）。

    调用方 bug（缺字段/超批量/越权），不应重试、不触发降级。
    """

    def __init__(self, code: str, message: str = "", http_status: int | None = None):
        super().__init__(f"[{http_status or ''} {code}] {message}")
        self.code = code
        self.message = message
        self.http_status = http_status


class KnowledgeGatewayError(Exception):
    """网关不可用（连接失败 / service_degraded / 5xx）——触发 Embedded 降级。"""

    def __init__(self, message: str, *, degraded: bool = False):
        super().__init__(message)
        self.degraded = degraded
