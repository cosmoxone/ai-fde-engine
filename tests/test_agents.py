"""
Agent模块测试
"""

import os

import pytest

from src.agents.base import AgentResult
from src.agents.delivery import DeliveryAgent
from src.agents.design import DesignAgent
from src.agents.project import ProjectAgent
from src.agents.research import ResearchAgent


@pytest.fixture
def research_agent(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    return ResearchAgent("test_project")


@pytest.fixture
def design_agent(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    return DesignAgent("test_project")


@pytest.fixture
def delivery_agent(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    return DeliveryAgent("test_project")


@pytest.fixture
def project_agent(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    return ProjectAgent("test_project")


class TestBaseAgent:
    """Agent基类测试"""

    def test_agent_result_to_dict(self):
        result = AgentResult(success=True, content="test", duration_seconds=1.5)
        d = result.to_dict()
        assert d["success"] is True
        assert d["content"] == "test"
        assert d["duration_seconds"] == 1.5

    def test_agent_result_failed(self):
        result = AgentResult(success=False, error="test error")
        assert result.success is False
        assert result.error == "test error"


class TestResearchAgent:
    """调研分析Agent测试"""

    def test_agent_type(self, research_agent):
        assert research_agent.agent_type == "research"
        assert research_agent.agent_name == "调研分析Agent"

    def test_system_prompt_not_empty(self, research_agent):
        prompt = research_agent.get_system_prompt()
        assert len(prompt) > 100
        assert "业务流程" in prompt
        assert "Benchmark" in prompt
        assert "需求" in prompt

    @pytest.mark.asyncio
    async def test_run_with_documents(self, research_agent):
        result = await research_agent.execute(
            {
                "documents": [
                    {
                        "filename": "业务手册.pdf",
                        "content": "业务流程包括受理、审核、处理。审核标准包括完整性和合规性。",
                    }
                ],
                "client_requirements": "需要一个智能审核助手",
            }
        )
        assert result.success is True
        assert result.structured_output is not None
        assert "business_process" in result.structured_output
        assert "requirements" in result.structured_output
        assert "benchmark" in result.structured_output
        assert "data_assets" in result.structured_output
        assert result.metadata["document_count"] == 1
        assert result.metadata["requirement_count"] > 0

    @pytest.mark.asyncio
    async def test_run_empty_input(self, research_agent):
        result = await research_agent.execute({"documents": []})
        assert result.success is True
        assert result.structured_output is not None

    @pytest.mark.asyncio
    async def test_requirements_have_priority(self, research_agent):
        result = await research_agent.execute(
            {
                "documents": [{"content": "测试业务文档"}],
            }
        )
        reqs = result.structured_output["requirements"]["functional"]
        assert len(reqs) > 0
        for req in reqs:
            assert "id" in req
            assert "title" in req
            assert "priority" in req
            assert "acceptance_criteria" in req

    @pytest.mark.asyncio
    async def test_benchmark_has_categories(self, research_agent):
        result = await research_agent.execute(
            {
                "documents": [{"content": "测试业务文档"}],
            }
        )
        bm = result.structured_output["benchmark"]
        assert "test_cases" in bm
        assert "acceptance_criteria" in bm
        categories = set(tc["category"] for tc in bm["test_cases"])
        assert "high_frequency" in categories


class TestDesignAgent:
    """方案设计Agent测试"""

    def test_agent_type(self, design_agent):
        assert design_agent.agent_type == "design"

    def test_system_prompt(self, design_agent):
        prompt = design_agent.get_system_prompt()
        assert "产品方案" in prompt
        assert "技术方案" in prompt
        assert "验证方案" in prompt

    @pytest.mark.asyncio
    async def test_run_design(self, design_agent):
        result = await design_agent.execute(
            {
                "requirements_baseline": {
                    "requirements": {"functional": [{"id": "R1", "title": "智能审核"}]},
                    "business_process": {"nodes": []},
                    "benchmark": {"test_cases": []},
                },
            }
        )
        assert result.success is True
        assert "product_solution" in result.structured_output
        assert "tech_solution" in result.structured_output
        assert "validation_solution" in result.structured_output
        assert "cross_check" in result.structured_output

    @pytest.mark.asyncio
    async def test_tech_solution_has_stack(self, design_agent):
        result = await design_agent.execute({"requirements_baseline": {}})
        tech = result.structured_output["tech_solution"]
        assert "tech_stack" in tech
        assert "architecture_mermaid" in tech
        assert "interfaces" in tech
        assert "deployment" in tech
        assert "risks" in tech

    @pytest.mark.asyncio
    async def test_cross_validation(self, design_agent):
        result = await design_agent.execute({"requirements_baseline": {}})
        cc = result.structured_output["cross_check"]
        assert "consistent" in cc
        assert "issues" in cc


class TestDeliveryAgent:
    """开发交付Agent测试"""

    def test_agent_type(self, delivery_agent):
        assert delivery_agent.agent_type == "delivery"

    @pytest.mark.asyncio
    async def test_generate_code(self, delivery_agent):
        result = await delivery_agent.execute(
            {
                "task_type": "generate_code",
                "tech_solution": {},
                "requirements": [{"id": "R1", "title": "测试功能"}],
                "project_name": "test_project",
            }
        )
        assert result.success is True
        assert "workspace_path" in result.structured_output
        assert "files_generated" in result.structured_output
        assert result.structured_output["files_generated"] > 0

    @pytest.mark.asyncio
    async def test_build_kb(self, delivery_agent):
        result = await delivery_agent.execute(
            {
                "task_type": "build_kb",
                "documents": [{"content": "测试文档"}],
                "kb_name": "test_kb",
            }
        )
        assert result.success is True
        assert result.structured_output["status"] == "ready"

    @pytest.mark.asyncio
    async def test_fix_badcase(self, delivery_agent):
        result = await delivery_agent.execute(
            {
                "task_type": "fix_badcase",
                "badcases": [
                    {"id": "B1", "input": "不知道答案", "actual_output": "未找到相关信息", "error_type": ""},
                    {"id": "B2", "input": "格式错误", "actual_output": "输出格式不对", "error_type": ""},
                ],
            }
        )
        assert result.success is True
        assert "fixed_count" in result.structured_output
        assert "need_human_count" in result.structured_output

    @pytest.mark.asyncio
    async def test_nightly_iteration(self, delivery_agent):
        result = await delivery_agent.execute(
            {
                "task_type": "nightly_iteration",
                "badcases": [{"id": "B1", "input": "测试", "actual_output": "不知道", "severity": "major"}],
                "iteration_number": 1,
            }
        )
        assert result.success is True
        assert "version" in result.structured_output
        assert "regression" in result.structured_output
        assert "deployment" in result.structured_output

    def test_badcase_attribution(self, delivery_agent):
        """测试Badcase归因"""
        # 知识库类
        attr = delivery_agent._attribute_badcase({"input": "测试", "actual_output": "不知道，未找到相关信息"})
        assert attr["type"] == "knowledge"
        assert attr["auto_fixable"] is True

        # 业务规则类
        attr = delivery_agent._attribute_badcase({"input": "测试", "actual_output": "规则冲突，特殊情况"})
        assert attr["type"] == "rule"
        assert attr["auto_fixable"] is False


class TestProjectAgent:
    """项目管控Agent测试"""

    def test_agent_type(self, project_agent):
        assert project_agent.agent_type == "project"

    @pytest.mark.asyncio
    async def test_progress_report(self, project_agent):
        result = await project_agent.execute(
            {
                "task_type": "progress_report",
                "project_data": {"name": "测试项目", "status": "research"},
                "tasks": [
                    {"id": "T1", "title": "调研", "status": "completed"},
                    {"id": "T2", "title": "设计", "status": "running"},
                ],
            }
        )
        assert result.success is True
        assert "overall_progress" in result.structured_output
        assert result.structured_output["overall_progress"] == 0.5
        assert "health_status" in result.structured_output

    @pytest.mark.asyncio
    async def test_risk_alert(self, project_agent):
        result = await project_agent.execute(
            {
                "task_type": "risk_alert",
                "project_data": {"status": "iteration"},
            }
        )
        assert result.success is True
        assert "risks" in result.structured_output
        assert len(result.structured_output["risks"]) > 0

    @pytest.mark.asyncio
    async def test_weekly_report(self, project_agent):
        result = await project_agent.execute({"task_type": "weekly_report"})
        assert result.success is True
        assert "completed_this_week" in result.structured_output
        assert "planned_next_week" in result.structured_output

    @pytest.mark.asyncio
    async def test_retrospective(self, project_agent):
        result = await project_agent.execute({"task_type": "retrospective"})
        assert result.success is True
        assert "what_went_well" in result.structured_output
        assert "what_to_improve" in result.structured_output
        assert "action_items" in result.structured_output

    @pytest.mark.asyncio
    async def test_asset_sediment(self, project_agent):
        result = await project_agent.execute(
            {
                "task_type": "asset_sediment",
                "assets": [
                    {"type": "best_practice", "content": "Benchmark前置可以减少需求扯皮", "reusable": True},
                    {"type": "component", "content": "通用文档解析组件", "reusable": True},
                ],
            }
        )
        assert result.success is True
        assert result.structured_output["sedimented_count"] == 2
