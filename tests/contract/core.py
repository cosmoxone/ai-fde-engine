"""场景内核:与报文形态无关的知识库契约场景(规格 14 v1.2 语义)。

架构:
- 本模块定义归一化类型(DocSpec/Hit/Stats…)与最小客户端面(KBClient);
- 断言适配(adapters_spec14 / adapters_kbos)把各自报文形态归一化到本模块;
- 同一组场景测试(test_kb_contract.py)即可对任意实现跑 —— W3 对拍基础。

契约源:docs/14-知识库接口规格.md v1.2。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

# ---------- 归一化数据类型 ----------


@dataclass
class DocSpec:
    """文档级推送单元(主协议)"""

    title: str
    content: str
    metadata: dict


@dataclass
class EntrySpec:
    """知识条目草稿"""

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
    """溯源五字段(规格 §3.2 必填)"""

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
    documents: int
    parsing: int
    curated: int
    pending: int
    chunks: int | None = None
    parse_failed: int | None = None
    rejected: int | None = None


class KBError(Exception):
    """归一化错误:http_status + 稳定字符串码(规格 §4 错误码表)"""

    def __init__(self, http_status: int, code: str, message: str = ""):
        super().__init__(f"[{http_status} {code}] {message}")
        self.http_status = http_status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Expectations:
    """适配层差异化的错误码预期(同一场景、不同实现的合法响应集合)。

    over_limit: 超批量推送的合法错误码
      - spec14: 413 payload_too_large(规格 §4)
      - kbos:   40001 invalid_request(kb-os 以参数非法等价实现,见 09 方案 §4.1.1)
    """

    over_limit: frozenset = frozenset({"payload_too_large", "invalid_request"})


# ---------- 最小客户端面(适配器实现) ----------


class KBClient:
    """契约场景所依赖的客户端抽象;两个适配器各自实现全部方法。"""

    profile: str = "abstract"
    expectations: Expectations = Expectations()

    # --- 观测面 ---
    def health(self) -> dict:
        raise NotImplementedError

    def stats(self) -> Stats:
        raise NotImplementedError

    # --- P0:上传→建库→检索 ---
    def ingest_documents(self, docs: list[DocSpec]) -> tuple[int, int]:
        """返回 (accepted, deduped);200=持久接受,最终一致"""
        raise NotImplementedError

    def search(self, query: str, top_k: int = 5) -> list[Hit]:
        raise NotImplementedError

    # --- P1:审核交互闭环 ---
    def curate(self, entry: EntrySpec) -> tuple[str, str]:
        """返回 (entry_id, status='pending')"""
        raise NotImplementedError

    def list_pending(self, page: int = 1, page_size: int = 50) -> tuple[int, list[dict]]:
        """返回 (total, entries);页码分页(规格 §3.4)"""
        raise NotImplementedError

    def confirm(self, entry_id: str, edited: dict | None = None) -> str:
        """返回终态 status;幂等(重复返回当前终态)"""
        raise NotImplementedError

    def reject(self, entry_id: str, reason: str | None = None) -> str:
        raise NotImplementedError

    # --- 错误分支触发器(负例场景) ---
    def trigger_invalid_request(self) -> None:
        """发出一个必然 invalid_request 的请求(如缺 query 的 search)"""
        raise NotImplementedError

    def trigger_over_limit(self) -> None:
        """发出一个必然超批量的 ingest(51 篇文档)"""
        raise NotImplementedError

    def probe_no_auth(self) -> tuple[int, str | None]:
        """不带凭证探测只读端点;返回 (http_status, 归一化错误码)"""
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------- 场景物料工厂(唯一标记保证断言确定性) ----------


def marker_token() -> str:
    """本次运行的全局唯一检索标记(字母数字,FTS/向量均可命中)"""
    return "ZZCONTRACT" + uuid.uuid4().hex[:10].upper()


def make_doc(marker: str, idx: int) -> DocSpec:
    return DocSpec(
        title=f"contract-probe-{marker}-{idx}.md",
        content=(f"{marker} 第{idx}条:让步放行需取得客户书面特采许可,经MRB评审,放行后记录追溯。{marker}"),
        metadata={
            "doc_id": f"contract-{marker}-{idx}",
            "title_path": "契约测试>探针",
            "entity_hints": ["特采", "MRB"],
            "origin": "contract-test",
        },
    )


def make_entry(marker: str, idx: int) -> EntrySpec:
    return EntrySpec(
        question_pattern=f"{marker} 光洁度不达标但尺寸合格能否放行?",
        answer=f"{marker} 不能直接放行。需提交MRB评审,取得客户书面特采许可后方可放行,并记录追溯。",
        origin=f"badcase:contract-{marker}-{idx}",
        suggested_by="contract-test",
    )
