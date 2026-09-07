"""
F7自助交付模块测试
覆盖：SelfServiceAgent + 自助交付API端点 + 后台Review + 纠偏检测
"""

import pytest
from fastapi.testclient import TestClient

from src.agents.self_service import SelfServiceAgent
from src.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    resp = client.post(
        "/api/v1/projects",
        json={
            "name": "自助交付测试项目",
            "client_name": "测试客户",
            "industry": "电子商务",
            "description": "自助交付模块测试",
        },
    )
    return resp.json().get("project", {}).get("id")


@pytest.fixture
def agent(project):
    return SelfServiceAgent(project)


# ============================================================
# SelfServiceAgent 单元测试
# ============================================================


class TestSelfServiceAgentInit:
    """Agent初始化测试"""

    def test_agent_creation(self, agent):
        """测试Agent创建成功"""
        assert agent.agent_type == "self_service"
        assert agent.project_id is not None

    def test_guidance_steps_initialized(self, agent):
        """测试引导步骤初始化"""
        assert len(agent.guidance_steps) == 5
        step_names = [s.step_name for s in agent.guidance_steps]
        assert "AI落地启蒙" in step_names
        assert "需求自主梳理" in step_names
        assert "方案自助配置" in step_names
        assert "原型试用验证" in step_names
        assert "价值确认与决策" in step_names

    def test_first_step_is_enlightenment(self, agent):
        """测试第一步是AI落地启蒙"""
        current = agent.get_current_step()
        assert current is not None
        assert current.step_id == "enlightenment"

    def test_guidance_progress_initial(self, agent):
        """测试初始进度为0%"""
        progress = agent.get_guidance_progress()
        assert progress["total_steps"] == 5
        assert progress["completed_steps"] == 0
        assert progress["progress_percentage"] == 0.0


class TestGuidanceFlow:
    """引导流程测试"""

    def test_complete_first_step(self, agent):
        """测试完成第一步"""
        result = agent._complete_step_sync("enlightenment", confirmation=True)
        assert result.success
        assert result.structured_output["completed_step"] == "enlightenment"
        assert result.structured_output["next_step"] == "requirement"

    def test_complete_step_without_confirmation_fails(self, agent):
        """测试未确认不能完成步骤"""
        result = agent._complete_step_sync("enlightenment", confirmation=False)
        assert not result.success
        assert "确认" in result.error

    def test_complete_nonexistent_step_fails(self, agent):
        """测试完成不存在的步骤失败"""
        result = agent._complete_step_sync("nonexistent", confirmation=True)
        assert not result.success

    def test_complete_all_steps(self, agent):
        """测试完成所有步骤"""
        for step_id in ["enlightenment", "requirement", "solution", "prototype", "decision"]:
            result = agent._complete_step_sync(step_id, confirmation=True)
            assert result.success
        progress = agent.get_guidance_progress()
        assert progress["completed_steps"] == 5
        assert progress["progress_percentage"] == 100.0
        assert agent.get_current_step() is None


class TestOpportunityIdentification:
    """AI落地机会识别测试"""

    @pytest.mark.asyncio
    async def test_identify_opportunities(self, agent):
        """测试识别AI落地机会"""
        result = await agent.run(
            {
                "task_type": "identify_opportunities",
                "business_description": "电商客服系统，日均5万条咨询",
                "industry": "电子商务",
                "pain_points": ["人工客服成本高", "响应时间长"],
            }
        )
        assert result.success
        assert len(result.structured_output["opportunities"]) > 0
        opp = result.structured_output["opportunities"][0]
        assert "title" in opp
        assert "roi_score" in opp
        assert "estimated_efficiency_gain" in opp

    @pytest.mark.asyncio
    async def test_opportunity_has_recommendation(self, agent):
        """测试机会识别返回推荐机会"""
        result = await agent.run(
            {
                "task_type": "identify_opportunities",
                "business_description": "测试业务",
            }
        )
        assert result.structured_output["recommended_opportunity"] is not None


class TestRequirementGuidance:
    """需求自助梳理测试"""

    @pytest.mark.asyncio
    async def test_generate_requirement_draft(self, agent):
        """测试生成需求初稿"""
        result = await agent.run(
            {
                "task_type": "guide_requirement",
                "action": "generate_draft",
            }
        )
        assert result.success
        assert "requirement_draft" in result.structured_output
        assert len(result.structured_output["requirement_draft"]["requirements"]) > 0

    @pytest.mark.asyncio
    async def test_confirm_requirement(self, agent):
        """测试确认需求基线"""
        result = await agent.run(
            {
                "task_type": "guide_requirement",
                "action": "confirm",
                "requirement_draft": {"test": "data"},
                "user_feedback": "确认无误",
            }
        )
        assert result.success
        assert result.structured_output["confirmed"] is True
        assert result.structured_output["baseline_version"] == "v1.0"

    @pytest.mark.asyncio
    async def test_modify_requirement(self, agent):
        """测试修改需求"""
        result = await agent.run(
            {
                "task_type": "guide_requirement",
                "action": "modify",
                "requirement_draft": {"R1": {"title": "原标题"}},
                "modified_requirements": {"R1": {"title": "新标题"}},
            }
        )
        assert result.success
        assert result.structured_output["requirement_draft"]["R1"]["title"] == "新标题"

    @pytest.mark.asyncio
    async def test_add_requirement(self, agent):
        """测试补充需求"""
        result = await agent.run(
            {
                "task_type": "guide_requirement",
                "action": "add",
                "requirement_draft": {"requirements": [{"id": "R1"}]},
                "new_requirements": [{"id": "R4", "title": "新需求"}],
            }
        )
        assert result.success
        assert result.structured_output["added_items"][0]["id"] == "R4"


class TestSolutionConfiguration:
    """方案自助配置测试"""

    @pytest.mark.asyncio
    async def test_configure_solution(self, agent):
        """测试方案配置"""
        result = await agent.run(
            {
                "task_type": "configure_solution",
                "selected_modules": ["智能客服", "知识库问答"],
                "deployment_mode": "saas",
                "integration_level": "basic",
            }
        )
        assert result.success
        assert "solution" in result.structured_output
        assert "cost_estimate" in result.structured_output["solution"]

    @pytest.mark.asyncio
    async def test_solution_cost_calculation(self, agent):
        """测试方案成本估算"""
        result = await agent.run(
            {
                "task_type": "configure_solution",
                "selected_modules": ["A", "B", "C"],
                "deployment_mode": "private",
                "integration_level": "deep",
            }
        )
        cost = result.structured_output["solution"]["cost_estimate"]
        assert cost["development"] > 0
        assert cost["annual_total"] > cost["development"]


class TestPrototypeGeneration:
    """原型生成测试"""

    @pytest.mark.asyncio
    async def test_generate_prototype(self, agent):
        """测试生成原型"""
        result = await agent.run(
            {
                "task_type": "generate_prototype",
                "prototype_type": "knowledge_base_qa",
                "config": {"name": "测试原型"},
            }
        )
        assert result.success
        proto = result.structured_output["prototype"]
        assert proto["status"] == "ready"
        assert "access_url" in proto
        assert proto["setup_time_seconds"] > 0


class TestValueCalculation:
    """价值计算测试"""

    @pytest.mark.asyncio
    async def test_calculate_value(self, agent):
        """测试价值计算"""
        result = await agent.run(
            {
                "task_type": "calculate_value",
                "baseline": {"review_time": 30, "cs_cost": 200000},
                "current": {"review_time": 9, "cs_cost": 80000},
                "investment": 100000,
            }
        )
        assert result.success
        metrics = result.structured_output["metrics"]
        assert len(metrics) == 4
        assert result.structured_output["summary"]["average_improvement"] > 0
        assert "roi_calculation" in result.structured_output

    @pytest.mark.asyncio
    async def test_value_metric_categories(self, agent):
        """测试价值指标包含四个维度"""
        result = await agent.run({"task_type": "calculate_value"})
        categories = [m["category"] for m in result.structured_output["metrics"]]
        assert "efficiency" in categories
        assert "cost" in categories
        assert "quality" in categories
        assert "satisfaction" in categories


class TestDeviationDetection:
    """纠偏检测测试"""

    def test_detect_vague_requirements(self, agent):
        """测试检测模糊需求"""
        alerts = agent._detect_deviations(
            {
                "requirements": [
                    {"description": "短"},
                    {"description": "也短"},
                    {"description": "这个描述足够长足够详细"},
                ]
            }
        )
        assert any(a["type"] == "vague_requirement" for a in alerts)

    def test_detect_scope_creep(self, agent):
        """测试检测范围蔓延（功能模块过多）"""
        alerts = agent._detect_deviations(
            {
                "selected_modules": ["A", "B", "C", "D", "E", "F"],
            }
        )
        assert any(a["type"] == "scope_creep" for a in alerts)
        assert any(a["severity"] == "high" for a in alerts)

    def test_detect_budget_mismatch(self, agent):
        """测试检测预算不匹配"""
        alerts = agent._detect_deviations(
            {
                "selected_modules": ["A", "B", "C", "D"],
                "budget": 30000,
            }
        )
        assert any(a["type"] == "budget_mismatch" for a in alerts)

    def test_detect_skipped_critical_step(self, agent):
        """测试检测跳过关键步骤"""
        alerts = agent._detect_deviations(
            {
                "skipped_steps": ["requirement", "solution"],
            }
        )
        assert any(a["type"] == "skipped_critical_step" for a in alerts)

    def test_no_deviation_for_normal_input(self, agent):
        """测试正常输入不产生纠偏"""
        alerts = agent._detect_deviations(
            {
                "selected_modules": ["A", "B"],
                "budget": 100000,
                "requirements": [{"description": "这是一个足够详细的需求描述，包含了具体的功能说明和使用场景"}],
            }
        )
        assert len(alerts) == 0


class TestFeedbackSubmission:
    """反馈提交测试"""

    @pytest.mark.asyncio
    async def test_submit_feedback(self, agent):
        """测试提交反馈"""
        result = await agent.run(
            {
                "task_type": "submit_feedback",
                "feedback_type": "bug",
                "content": "问答结果不准确",
                "rating": 2,
                "prototype_id": "proto-test",
            }
        )
        assert result.success
        fb = result.structured_output["feedback"]
        assert fb["type"] == "bug"
        assert fb["status"] == "pending_review"
        assert result.structured_output["priority"] == "high"

    @pytest.mark.asyncio
    async def test_general_feedback_priority(self, agent):
        """测试普通反馈优先级为medium"""
        result = await agent.run(
            {
                "task_type": "submit_feedback",
                "feedback_type": "general",
                "content": "建议增加导出功能",
                "rating": 4,
            }
        )
        assert result.structured_output["priority"] == "medium"


# ============================================================
# F7 API端点测试
# ============================================================


class TestF7API:
    """F7自助交付API测试"""

    def test_get_progress(self, client, project):
        """测试获取引导进度"""
        resp = client.get(f"/api/v1/projects/{project}/self-service/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["progress"]["total_steps"] == 5
        assert data["progress"]["completed_steps"] == 0

    def test_get_progress_nonexistent_project(self, client):
        """测试不存在项目的进度查询"""
        resp = client.get("/api/v1/projects/nonexistent/self-service/progress")
        assert resp.status_code == 404

    def test_identify_opportunities_api(self, client, project):
        """测试AI落地机会识别API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/opportunities",
            json={"business_description": "电商客服系统", "industry": "电商"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "task_id" in resp.json()

    def test_requirement_guide_api(self, client, project):
        """测试需求自助梳理API"""
        resp = client.post(f"/api/v1/projects/{project}/self-service/requirements", json={"action": "generate_draft"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "requirement_draft" in data["result"]

    def test_requirement_confirm_api(self, client, project):
        """测试需求确认API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/requirements",
            json={"action": "confirm", "requirement_draft": {"test": True}},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["confirmed"] is True

    def test_solution_config_api(self, client, project):
        """测试方案配置API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/solution",
            json={"selected_modules": ["智能客服"], "deployment_mode": "saas"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "solution" in data["result"]
        assert "deviation_alerts" in data

    def test_solution_config_with_scope_creep(self, client, project):
        """测试方案配置触发范围蔓延纠偏"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/solution",
            json={"selected_modules": ["A", "B", "C", "D", "E", "F"], "budget": 100000},
        )
        assert resp.status_code == 200
        alerts = resp.json()["deviation_alerts"]
        assert any(a["type"] == "scope_creep" for a in alerts)

    def test_prototype_generate_api(self, client, project):
        """测试原型生成API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/prototype",
            json={"prototype_type": "knowledge_base_qa", "config": {"name": "测试"}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["prototype"]["status"] == "ready"

    def test_value_dashboard_api(self, client, project):
        """测试价值仪表盘API"""
        resp = client.get(f"/api/v1/projects/{project}/self-service/value")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "metrics" in data["value"]
        assert len(data["value"]["metrics"]) == 4

    def test_value_calculate_api(self, client, project):
        """测试价值计算API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/value/calculate",
            json={"baseline": {}, "current": {}, "investment": 100000},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_feedback_submit_api(self, client, project):
        """测试反馈提交API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/feedback",
            json={"feedback_type": "bug", "content": "测试bug", "rating": 2},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_feedback_list_api(self, client, project):
        """测试反馈列表API"""
        # 先提交一个反馈
        client.post(
            f"/api/v1/projects/{project}/self-service/feedback", json={"feedback_type": "general", "content": "测试"}
        )
        resp = client.get(f"/api/v1/projects/{project}/self-service/feedback")
        assert resp.status_code == 200
        assert len(resp.json()["feedback"]) >= 1

    def test_complete_step_api(self, client, project):
        """测试完成步骤API"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/complete-step",
            json={"step_id": "enlightenment", "confirmation": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["completed_step"] == "enlightenment"
        assert data["result"]["next_step"] == "requirement"

    def test_complete_step_without_confirmation(self, client, project):
        """测试未确认完成步骤失败"""
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/complete-step",
            json={"step_id": "enlightenment", "confirmation": False},
        )
        assert resp.status_code == 400

    def test_deviation_alerts_api(self, client, project):
        """测试纠偏提醒API"""
        resp = client.get(f"/api/v1/projects/{project}/self-service/deviations")
        assert resp.status_code == 200
        assert "alerts" in resp.json()
        assert "needs_immediate_attention" in resp.json()


class TestF7ReviewAPI:
    """F7后台Review API测试"""

    def test_pending_review_list(self, client):
        """测试待审核列表"""
        resp = client.get("/api/v1/self-service/review/pending")
        assert resp.status_code == 200
        assert "pending_count" in resp.json()
        assert "reviews" in resp.json()

    def test_review_history(self, client):
        """测试审核历史"""
        resp = client.get("/api/v1/self-service/review/history")
        assert resp.status_code == 200
        assert "reviews" in resp.json()

    def test_review_action_nonexistent(self, client):
        """测试不存在的审核项操作"""
        resp = client.post(
            "/api/v1/self-service/review/nonexistent/action", json={"action": "approve", "comment": "通过"}
        )
        assert resp.status_code == 404


# ============================================================
# 端到端流程测试
# ============================================================


class TestF7EndToEnd:
    """F7自助交付端到端流程测试"""

    def test_full_self_service_flow(self, client, project):
        """测试完整自助交付流程：机会识别→需求梳理→方案配置→原型→价值"""
        # 1. AI落地机会识别
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/opportunities",
            json={"business_description": "电商客服", "industry": "电商"},
        )
        assert resp.status_code == 200

        # 2. 需求自助梳理 - 生成初稿
        resp = client.post(f"/api/v1/projects/{project}/self-service/requirements", json={"action": "generate_draft"})
        assert resp.status_code == 200
        draft = resp.json()["result"]["requirement_draft"]
        assert len(draft["requirements"]) > 0

        # 3. 确认需求
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/requirements",
            json={"action": "confirm", "requirement_draft": draft},
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["confirmed"] is True

        # 4. 方案配置
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/solution",
            json={"selected_modules": ["智能客服", "知识库"], "deployment_mode": "saas"},
        )
        assert resp.status_code == 200
        assert "cost_estimate" in resp.json()["result"]["solution"]

        # 5. 原型生成
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/prototype", json={"prototype_type": "knowledge_base_qa"}
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["prototype"]["status"] == "ready"

        # 6. 价值计算
        resp = client.post(f"/api/v1/projects/{project}/self-service/value/calculate", json={"investment": 100000})
        assert resp.status_code == 200
        assert resp.json()["result"]["summary"]["average_improvement"] > 0

        # 7. 提交反馈
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/feedback",
            json={"feedback_type": "praise", "content": "体验很好", "rating": 5},
        )
        assert resp.status_code == 200

        # 8. 完成所有引导步骤
        for step_id in ["enlightenment", "requirement", "solution", "prototype", "decision"]:
            resp = client.post(
                f"/api/v1/projects/{project}/self-service/complete-step",
                json={"step_id": step_id, "confirmation": True},
            )
            assert resp.status_code == 200

        # 9. 验证最终进度100%
        resp = client.get(f"/api/v1/projects/{project}/self-service/progress")
        assert resp.json()["progress"]["progress_percentage"] == 100.0
