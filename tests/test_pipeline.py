"""
流水线模块测试
"""

import os

import pytest

from src.pipeline.iteration import IterationResult, NightlyIterationPipeline


@pytest.fixture
def pipeline(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    os.environ["OPENHANDS_WORKSPACE_BASE"] = str(tmp_path)
    return NightlyIterationPipeline("test_project")


class TestIterationResult:
    """迭代结果测试"""

    def test_default_values(self):
        result = IterationResult(success=True, version="v0.1.1", iteration_number=1)
        assert result.success is True
        assert result.version == "v0.1.1"
        assert result.badcases_processed == 0
        assert result.gate_passed is False
        assert result.deployed is False


class TestNightlyIterationPipeline:
    """夜间迭代流水线测试"""

    @pytest.mark.asyncio
    async def test_run_full_pipeline(self, pipeline):
        badcases = [
            {"id": "B1", "input": "测试问题1", "actual_output": "不知道答案", "severity": "major"},
            {"id": "B2", "input": "测试问题2", "actual_output": "格式错误", "severity": "minor"},
            {"id": "B3", "input": "测试问题3", "actual_output": "规则冲突特殊情况", "severity": "critical"},
        ]
        result = await pipeline.run(badcases)
        assert result.success is True
        assert result.badcases_processed == 3
        assert result.auto_fixed + result.need_human == 3
        assert result.version.startswith("v0.1.")
        assert result.duration_seconds >= 0
        assert len(result.steps) >= 4  # 至少有数据归集、归因修复、回归测试、部署/回滚
        assert "夜间迭代报告" in result.report

    @pytest.mark.asyncio
    async def test_run_with_benchmark(self, pipeline):
        badcases = [{"id": "B1", "input": "test", "actual_output": "不知道", "severity": "major"}]
        benchmark_cases = [
            {"id": "T1", "input": "test", "expected_output": "expected", "category": "high_frequency"},
        ]
        result = await pipeline.run(badcases, benchmark_cases=benchmark_cases)
        assert result.success is True
        assert result.regression_accuracy > 0

    @pytest.mark.asyncio
    async def test_iteration_number(self, pipeline):
        result = await pipeline.run([], iteration_number=5)
        assert result.iteration_number == 5
        assert result.version == "v0.1.5"

    @pytest.mark.asyncio
    async def test_empty_badcases(self, pipeline):
        result = await pipeline.run([])
        assert result.success is True
        assert result.badcases_processed == 0
        assert result.auto_fixed == 0

    @pytest.mark.asyncio
    async def test_report_contains_sections(self, pipeline):
        result = await pipeline.run(
            [
                {"id": "B1", "input": "test", "actual_output": "不知道", "severity": "major"},
            ]
        )
        report = result.report
        assert "迭代概览" in report
        assert "执行步骤" in report
        assert "下一步" in report
        assert result.version in report

    @pytest.mark.asyncio
    async def test_steps_have_names(self, pipeline):
        result = await pipeline.run([{"id": "B1", "input": "test", "actual_output": "不知道", "severity": "major"}])
        step_names = [s["step"] for s in result.steps]
        assert "data_collection" in step_names
        assert "attribution_and_fix" in step_names
        assert "regression_test" in step_names

    @pytest.mark.asyncio
    async def test_pending_issues_for_human(self, pipeline):
        result = await pipeline.run(
            [
                {"id": "B1", "input": "test", "actual_output": "规则冲突，特殊情况", "severity": "major"},
            ]
        )
        # 规则冲突类问题应被标记为需人工处理
        assert result.need_human >= 1
        assert len(result.pending_issues) >= 1
