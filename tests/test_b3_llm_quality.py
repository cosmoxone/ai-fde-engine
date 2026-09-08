"""
B3 测试：LLM schema 校验重试 + 黄金集 + DesignAgent LLM 接入
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.design import DesignAgent
from src.evaluation.golden import GOLDEN_SAMPLES, GoldenSample, run_golden_eval


class TestCallLLMSchemaRetry:
    """_call_llm 缺字段自动重试（带错误反馈）"""

    @pytest.fixture
    def agent(self):
        return DesignAgent("retry-test")

    @pytest.mark.asyncio
    async def test_retry_on_missing_keys(self, agent):
        calls = []

        async def fake_chat_json(messages, model, temperature, **kwargs):
            calls.append([m.content for m in messages])
            if len(calls) == 1:
                return _FakeResp('{"summary": "only"}'), {"summary": "only"}
            return _FakeResp(
                '{"summary": "s", "product_solution": {}, "tech_solution": {}, "validation_solution": {}}'
            ), {
                "summary": "s",
                "product_solution": {},
                "tech_solution": {},
                "validation_solution": {},
            }

        with patch.object(agent.llm, "chat_json", side_effect=fake_chat_json):
            _, parsed = await agent._call_llm(
                user_prompt="p",
                response_json=True,
                required_keys=["summary", "product_solution", "tech_solution", "validation_solution"],
            )
        assert len(calls) == 2  # 重试了一次
        assert "缺少必需字段" in calls[1][-1]  # 重试带反馈
        assert "product_solution" in parsed

    @pytest.mark.asyncio
    async def test_no_retry_when_valid(self, agent):
        async def fake_chat_json(messages, model, temperature, **kwargs):
            return _FakeResp("{}"), {
                "summary": "s",
                "product_solution": {},
                "tech_solution": {},
                "validation_solution": {},
            }

        with patch.object(agent.llm, "chat_json", side_effect=fake_chat_json):
            _, parsed = await agent._call_llm("p", response_json=True, required_keys=["summary"])
        assert parsed["summary"] == "s"


class _FakeResp:
    def __init__(self, content):
        self.content = content


class TestDesignAgentLLMPath:
    @pytest.mark.asyncio
    async def test_real_llm_merges_mock_fields(self):
        """真实LLM输出 + mock补齐缺失字段"""
        agent = DesignAgent("design-llm")

        async def fake_call(user_prompt, temperature, response_json, required_keys, **kw):
            return "text", {"summary": "AI方案", "product_solution": {"features": [{"id": "F1"}]}}

        with (
            patch.object(agent, "_has_real_llm", return_value=True),
            patch.object(agent, "_call_llm", side_effect=fake_call),
        ):
            result = await agent._perform_design({}, {}, {}, "")
        assert result["summary"] == "AI方案"
        assert "tech_solution" in result  # mock 补齐
        assert "validation_solution" in result

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_mock(self):
        agent = DesignAgent("design-fallback")

        async def boom(**kw):
            raise RuntimeError("api down")

        with (
            patch.object(agent, "_has_real_llm", return_value=True),
            patch.object(agent, "_call_llm", side_effect=boom),
        ):
            result = await agent._perform_design({}, {}, {}, "")
        assert result["summary"]  # mock 兜底非空
        assert "product_solution" in result

    def test_build_design_prompt_contains_sections(self):
        agent = DesignAgent("design-prompt")
        prompt = agent._build_design_prompt({"requirements": []}, {}, {"test_cases": []}, "经验")
        assert "需求基线" in prompt
        assert "历史项目经验" in prompt
        assert "product_solution" in prompt


class TestGoldenSet:
    def test_20_samples_distribution(self):
        industries = [s.industry for s in GOLDEN_SAMPLES]
        assert len(GOLDEN_SAMPLES) == 20
        assert industries.count("制造业") == 8
        assert industries.count("金融业") == 6
        assert industries.count("政务") == 6

    def test_sample_structure(self):
        for s in GOLDEN_SAMPLES:
            assert isinstance(s, GoldenSample)
            assert s.doc_snippet and s.client_ask
            assert len(s.expected_points) >= 2, f"{s.sample_id} 要点过少"
            assert len(s.doc_snippet) >= 20

    @pytest.mark.asyncio
    async def test_eval_skips_in_mock_mode(self):
        result = await run_golden_eval()
        assert result["status"] == "skipped"
        assert result["total"] == 20
