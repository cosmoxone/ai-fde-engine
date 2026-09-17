"""v0.4-c 测试：research RAG 化三模式 + 本体注入 + badcase→CuratedEntry 闭环。

验收对齐（13 号 §五 c 行 / 决策依据 18 号）：
- 三模式行为正确（full 基线 / hybrid 默认 / rag 纯检索），KB 无命中自动回退 full；
- input_stats 成本对比数据（reduction = 1 - prompt/full）；
- 本体摘要注入 hybrid/rag；
- badcase knowledge 归因 → CuratedEntry 草稿进 pending 队列（人工确认门）；
- 黄金集 Mock 语义不倒退（test_b3 回归见全量）。
"""

from __future__ import annotations

import pytest

from src.agents.delivery import DeliveryAgent
from src.agents.research import ResearchAgent
from src.knowledge import get_knowledge_gateway
from src.ontology.service import extract_for_documents


async def _seed_kb_and_ontology(project_id: str) -> None:
    """造数据：1 篇长文档入 KB + 本体抽取（Embedded 全链路）。"""
    long_content = "# 来料检验流程\n\n" + (
        "来料检验IQC 负责物料入库质量把关，检验记录统一写入 MES检验记录系统，"
        "不合格品提交 MRB 评审并在 QMS不合格品数据 中登记追溯。 " * 30
    )
    gw = get_knowledge_gateway()
    from src.knowledge import DocSpec

    gw.ingest_documents(
        project_id,
        [
            DocSpec(
                title="质量手册.md",
                content=long_content,
                metadata={"doc_id": "kb-doc-1", "origin": "test"},
            )
        ],
    )
    await extract_for_documents(
        project_id, [{"id": "kb-doc-1", "filename": "质量手册.md", "parse_status": "parsed", "content": long_content}]
    )


async def _run_research(mode: str | None, monkeypatch=None, project: str = "rag-test-proj"):
    """模式注入用实例属性 setattr（monkeypatch 自动还原）——
    不动 get_settings 全局缓存（曾引发跨测试顺序耦合：settings_runtime 单例重建竞态）。"""
    agent = ResearchAgent(project)
    if mode and monkeypatch:
        monkeypatch.setattr(agent.settings, "research_rag_mode", mode)
    return await agent.execute(
        {
            "documents": [{"filename": "质量手册.md", "content": "来料检验IQC 流程" * 400}],
            "client_requirements": "需要一个来料检验智能助手",
        }
    )


class TestBenchmarkProvenance:
    """机制3（13 号 §3.3）：Benchmark 用例溯源——test_case.source = {filename, chunk_index}。"""

    @pytest.mark.asyncio
    async def test_hybrid_injects_source(self):
        from src.agents.research import ResearchAgent
        from src.knowledge import DocSpec, get_knowledge_gateway
        from src.ontology.service import extract_for_documents

        pid = "bench-prov-proj"
        gw = get_knowledge_gateway()
        gw.ingest_documents(
            pid,
            [
                DocSpec(
                    title="检验规程.md",
                    content="来料检验IQC 执行加严抽检 AQL 0.65，记录写入 MES检验记录。" * 30,
                    metadata={"doc_id": "bp-1"},
                )
            ],
        )
        await extract_for_documents(
            pid,
            [
                {
                    "id": "bp-1",
                    "filename": "检验规程.md",
                    "parse_status": "parsed",
                    "content": "来料检验IQC 执行加严抽检 AQL 0.65，记录写入 MES检验记录。" * 30,
                }
            ],
        )

        agent = ResearchAgent(pid)
        result = await agent.execute(
            {
                "documents": [{"filename": "检验规程.md", "content": "来料检验IQC 抽检规范与记录要求" * 200}],
                "client_requirements": "检验助手",
            }
        )
        cases = result.structured_output["benchmark"]["test_cases"]
        assert cases, "mock 应生成用例"
        with_source = [c for c in cases if c.get("source")]
        assert with_source, "hybrid 模式有用例应带 source 溯源"
        for c in with_source:
            assert c["source"]["filename"] == "检验规程.md"
            assert isinstance(c["source"]["chunk_index"], int)

    @pytest.mark.asyncio
    async def test_full_mode_no_source(self, monkeypatch):
        from src.agents.research import ResearchAgent

        agent = ResearchAgent("bench-prov-empty")
        monkeypatch.setattr(agent.settings, "research_rag_mode", "full")  # 单例属性须 monkeypatch（复盘 T-4）
        result = await agent.execute(
            {
                "documents": [{"filename": "d.txt", "content": "内容"}],
            }
        )
        cases = result.structured_output["benchmark"]["test_cases"]
        assert all(not c.get("source") for c in cases), "full 模式不注入（向后兼容）"


class TestRagModes:
    @pytest.mark.asyncio
    async def test_hybrid_default_with_kb_hits(self):
        await _seed_kb_and_ontology("rag-test-proj")
        result = await _run_research(None)  # 默认 hybrid
        stats = result.metadata["input_stats"]
        assert stats["mode_requested"] == "hybrid"
        assert stats["mode_effective"] == "hybrid"
        assert stats["kb_hits"] > 0, "KB 有数据时应命中检索块"
        assert stats["ontology_injected"] is True, "本体有数据时应注入摘要"
        assert stats["prompt_chars"] < stats["full_chars"], "hybrid 应比全文截断省"
        assert 0.0 <= stats["reduction"] <= 1.0

    @pytest.mark.asyncio
    async def test_rag_pure_mode(self, monkeypatch):
        await _seed_kb_and_ontology("rag-test-proj")
        big_doc = "来料检验IQC 流程" * 3500  # ~3.5 万字大语料（RAG 目标场景；小语料应回退 full）
        agent = ResearchAgent("rag-test-proj")
        monkeypatch.setattr(agent.settings, "research_rag_mode", "rag")
        result = await agent.execute(
            {
                "documents": [{"filename": "质量手册.md", "content": big_doc}],
                "client_requirements": "需要一个来料检验智能助手",
            }
        )
        stats = result.metadata["input_stats"]
        assert stats["mode_effective"] == "rag"
        assert stats["kb_hits"] > 0
        assert stats["reduction"] > 0.5, "纯检索模式注入量应大幅小于全文"
        assert result.success and "business_process" in result.structured_output

    @pytest.mark.asyncio
    async def test_full_mode_unchanged(self, monkeypatch):
        result = await _run_research("full", monkeypatch)
        stats = result.metadata["input_stats"]
        assert stats["mode_effective"] == "full"
        assert stats["prompt_chars"] == stats["full_chars"]
        assert stats["kb_hits"] == 0

    @pytest.mark.asyncio
    async def test_fallback_when_kb_empty(self, monkeypatch):
        """适用边界（18 号 §6）：小语料/无命中 → 自动回退 full，不报错。"""
        result = await _run_research("rag", monkeypatch, project="kb-empty-proj")  # 项目无任何 KB 数据
        stats = result.metadata["input_stats"]
        assert stats["mode_effective"] == "full-fallback"
        assert stats["fallback_reason"] == "no-kb-hits"
        assert result.success is True


class TestBadcaseCuratedLoop:
    @pytest.mark.asyncio
    async def test_knowledge_fix_creates_pending_entry(self):
        agent = DeliveryAgent("badcase-proj")
        result = await agent._apply_fix(
            {
                "input": "来料检验的AQL标准是多少",
                "expected_output": "AQL 0.65 加严抽检",
                "actual_output": "AQL 1.0 常规",
            },
            {"type": "knowledge", "reason": "知识库缺该规则"},
        )
        assert result["status"] == "fixed"
        assert result.get("kb_entry_id"), "应返回草稿 entry_id"
        total, entries = get_knowledge_gateway().list_pending("badcase-proj", 1, 20)
        assert total >= 1
        mine = [e for e in entries if e["draft"].get("origin") == "badcase-loop"]
        assert mine, "badcase 草稿应进入待确认队列（人工审核门）"
        # 幂等：重复提交不新增
        again = await agent._apply_fix(
            {"input": "来料检验的AQL标准是多少", "expected_output": "x", "actual_output": "y"},
            {"type": "knowledge", "reason": "r"},
        )
        total2, _ = get_knowledge_gateway().list_pending("badcase-proj", 1, 20)
        assert total2 == total
        assert again.get("kb_entry_id") == result["kb_entry_id"]

    @pytest.mark.asyncio
    async def test_kb_failure_does_not_block_fix(self):
        agent = DeliveryAgent("kb-down-proj")
        from unittest.mock import patch

        with patch("src.knowledge.get_knowledge_gateway", side_effect=RuntimeError("kb down")):
            result = await agent._apply_fix(
                {"input": "q", "expected_output": "e", "actual_output": "a"},
                {"type": "knowledge", "reason": "r"},
            )
        assert result["status"] == "fixed" and "kb_entry_id" not in result
