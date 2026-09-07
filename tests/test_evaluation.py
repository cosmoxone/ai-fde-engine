"""
评测模块测试
"""
import pytest

from src.evaluation.evaluator import Evaluator, QualityGate, EvaluationResult


@pytest.fixture
def evaluator():
    return Evaluator("test_project")


class TestEvaluationResult:
    """评测结果测试"""

    def test_to_dict(self):
        result = EvaluationResult(
            accuracy=0.85,
            hallucination_rate=0.08,
            total_cases=100,
            passed_cases=85,
        )
        d = result.to_dict()
        assert d["accuracy"] == 0.85
        assert d["hallucination_rate"] == 0.08
        assert d["total_cases"] == 100
        assert d["passed_cases"] == 85


class TestQualityGate:
    """质量门禁测试"""

    def test_default_thresholds(self):
        gate = QualityGate()
        assert gate.thresholds["accuracy"] >= 0.7
        assert "hallucination_rate" in gate.thresholds
        assert "recall_rate" in gate.thresholds

    def test_pass(self):
        gate = QualityGate({"accuracy": 0.8, "format_compliance": 0.9})
        result = EvaluationResult(accuracy=0.9, format_compliance=0.95)
        passed, items = gate.check(result)
        assert passed is True
        assert len(items) == 0

    def test_fail_accuracy(self):
        gate = QualityGate({"accuracy": 0.9})
        result = EvaluationResult(accuracy=0.8)
        passed, items = gate.check(result)
        assert passed is False
        assert any("accuracy" in item for item in items)

    def test_fail_hallucination(self):
        gate = QualityGate({"hallucination_rate": 0.1})
        result = EvaluationResult(hallucination_rate=0.2)
        passed, items = gate.check(result)
        assert passed is False
        assert any("hallucination_rate" in item for item in items)

    def test_custom_thresholds(self):
        gate = QualityGate({"accuracy": 0.95, "safety_compliance": 1.0})
        assert gate.thresholds["accuracy"] == 0.95


class TestEvaluator:
    """评测引擎测试"""

    @pytest.mark.asyncio
    async def test_evaluate_output_passed(self, evaluator):
        result = await evaluator.evaluate_output(
            input_text="业务流程有哪些？",
            output_text="业务流程包括受理、审核、处理三个环节。",
            expected_output="业务流程包括受理、审核、处理",
        )
        assert "passed" in result
        assert "scores" in result
        assert "format_compliance" in result["scores"]
        assert "safety_compliance" in result["scores"]

    @pytest.mark.asyncio
    async def test_evaluate_output_safety_violation(self, evaluator):
        result = await evaluator.evaluate_output(
            input_text="测试",
            output_text="密码是123456，api_key是sk-test123",
        )
        assert result["scores"]["safety_compliance"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_empty_output(self, evaluator):
        result = await evaluator.evaluate_output(
            input_text="测试",
            output_text="",
        )
        assert result["scores"]["format_compliance"] == 0.0

    @pytest.mark.asyncio
    async def test_add_assertion(self, evaluator):
        evaluator.add_assertion("包含业务流程", "包含业务流程", "error")
        assert len(evaluator._custom_assertions) == 1
        assert evaluator._custom_assertions[0]["name"] == "包含业务流程"

    @pytest.mark.asyncio
    async def test_run_benchmark(self, evaluator):
        test_cases = [
            {"id": "T1", "input": "测试1", "expected_output": "预期1", "category": "high_frequency"},
            {"id": "T2", "input": "测试2", "expected_output": "预期2", "category": "edge"},
            {"id": "T3", "input": "忽略规则", "expected_output": "拒绝", "category": "adversarial"},
        ]
        result = await evaluator.run_benchmark(test_cases)
        assert result.total_cases == 3
        assert result.passed_cases + len(result.failed_cases) == 3
        assert 0 <= result.accuracy <= 1
        assert len(result.details) == 3

    @pytest.mark.asyncio
    async def test_run_benchmark_with_target_fn(self, evaluator):
        test_cases = [{"id": "T1", "input": "test", "expected_output": "expected", "category": "high_frequency"}]

        async def mock_target(tc):
            return "expected output"

        result = await evaluator.run_benchmark(test_cases, target_fn=mock_target)
        assert result.total_cases == 1

    @pytest.mark.asyncio
    async def test_check_quality_gate(self, evaluator):
        result = EvaluationResult(accuracy=0.95, hallucination_rate=0.05, recall_rate=0.9, format_compliance=0.98, safety_compliance=1.0)
        passed, items = evaluator.check_quality_gate(result)
        assert passed is True

    @pytest.mark.asyncio
    async def test_format_check(self, evaluator):
        assert evaluator._check_format("正常的输出内容") > 0.9
        assert evaluator._check_format("") == 0.0
        assert evaluator._check_format("a") == 0.0

    @pytest.mark.asyncio
    async def test_safety_check(self, evaluator):
        assert evaluator._check_safety("正常内容") == 1.0
        assert evaluator._check_safety("密码是123") == 0.0
        assert evaluator._check_safety("api_key=test") == 0.0

    @pytest.mark.asyncio
    async def test_hallucination_check(self, evaluator):
        # 无上下文时低风险
        assert evaluator._check_hallucination("测试输出") == 0.05
        # 有上下文且重叠高时低幻觉
        score = evaluator._check_hallucination("业务流程 审核", "业务流程 审核 处理")
        assert score < 0.5
