"""
D3 公开基准报告测试
"""

from __future__ import annotations

import pytest

from src.evaluation.benchmark_report import render_report, run_benchmark_report


class TestBenchmarkReport:
    @pytest.mark.asyncio
    async def test_report_covers_three_industries(self):
        data = await run_benchmark_report()
        assert set(data["by_industry"].keys()) == {"manufacturing", "finance", "government"}
        for m in data["by_industry"].values():
            assert m["cases"] >= 3
            assert 0.0 <= m["accuracy"] <= 1.0
            assert isinstance(m["gate_passed"], bool)

    @pytest.mark.asyncio
    async def test_report_mode_and_golden_set(self):
        data = await run_benchmark_report()
        assert data["mode"] in ("mock-baseline", "real-llm")
        assert data["golden_set"]["total"] == 20
        assert sum(data["golden_set"]["industries"].values()) == 20

    def test_render_markdown(self):
        data = {
            "generated_at": "2026-09-07 22:00",
            "mode": "mock-baseline",
            "by_industry": {
                "manufacturing": {
                    "industry": "制造业",
                    "cases": 3,
                    "accuracy": 0.9,
                    "hallucination_rate": 0.05,
                    "recall_rate": 0.8,
                    "format_compliance": 1.0,
                    "gate_passed": True,
                }
            },
            "golden_set": {"total": 20, "industries": {"制造业": 8, "金融业": 6, "政务": 6}},
            "note": "mock-baseline",
        }
        md = render_report(data)
        assert "公开评测基准" in md
        assert "制造业" in md
        assert "复现方式" in md
        assert "黄金集" in md
