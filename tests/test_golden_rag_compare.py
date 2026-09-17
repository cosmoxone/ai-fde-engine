"""v0.4 RAG 黄金集两栏对比机制测试（18 号 ADR 终验协议）。

无 Key 环境：compare 与单模式均 skipped（与 run_golden_eval 同语义）；
机制就绪性（参数路由/判据逻辑）用 mock 侧验证。
"""

from __future__ import annotations

import pytest

from src.evaluation.golden import run_golden_eval, run_golden_rag_compare


class TestGoldenRagCompare:
    @pytest.mark.asyncio
    async def test_skipped_without_key(self):
        """无 Key：两栏对比返回 skipped（不报错、可重复调用）。"""
        result = await run_golden_rag_compare()
        assert result["status"] == "skipped"
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_single_mode_skipped_without_key(self):
        assert (await run_golden_eval(rag_mode="full"))["status"] == "skipped"
        assert (await run_golden_eval(rag_mode="hybrid"))["status"] == "skipped"

    def test_verdict_logic_unit(self):
        """判据单元验证：hybrid ≥ full → pass；否则 regress（纯逻辑，不依赖 Key）。"""
        # 直接验证判据表达式语义（columns 构造走 monkeypatch run_golden_eval）
        import asyncio

        from src.evaluation.golden import run_golden_rag_compare as _cmp

        async def fake_eval(provider_filter=None, rag_mode=None):
            return {
                "status": "done",
                "hit_rate": 0.9 if rag_mode == "hybrid" else 0.95,
                "input_stats": {"avg_reduction": 0.5 if rag_mode == "hybrid" else 0.0},
            }

        import src.evaluation.golden as g

        orig = g.run_golden_eval
        g.run_golden_eval = fake_eval
        try:
            result = asyncio.run(_cmp())
            assert result["verdict"] == "regress", "hybrid 0.9 < full 0.95 应判回退"

            async def fake2(provider_filter=None, rag_mode=None):
                return {
                    "status": "done",
                    "hit_rate": 0.95 if rag_mode == "hybrid" else 0.95,
                    "input_stats": {"avg_reduction": 0.5 if rag_mode == "hybrid" else 0.0},
                }

            g.run_golden_eval = fake2
            result2 = asyncio.run(_cmp())
            assert result2["verdict"] == "pass"
        finally:
            g.run_golden_eval = orig
