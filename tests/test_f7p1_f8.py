"""
F7 P1增强功能 + F8培训模块 集成测试
覆盖：F7.10培训推送/F7.11客户成长路径/F7.12付费转化/F7.13沟通通道
      F8能力模型/学习路径/AI教练/实战沙箱/知识库/考核认证
"""

import pytest
from fastapi.testclient import TestClient

from src.agents.training import TrainingAgent
from src.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    resp = client.post("/api/v1/projects", json={"name": "F7P1/F8测试项目", "industry": "金融"})
    return resp.json()["project"]["id"]


@pytest.fixture
def training_agent():
    return TrainingAgent(project_id="test-training", learner_id="test-learner")


# ============================================================
# F7 P1 功能测试
# ============================================================


class TestF7P1TrainingPush:
    """F7.10 培训内容推送"""

    def test_push_training_api(self, client, project):
        resp = client.post(f"/api/v1/projects/{project}/self-service/training/push")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "training_contents" in data["result"]
        assert len(data["result"]["training_contents"]) > 0

    def test_training_content_structure(self, client, project):
        resp = client.post(f"/api/v1/projects/{project}/self-service/training/push")
        contents = resp.json()["result"]["training_contents"]
        for c in contents:
            assert "id" in c
            assert "title" in c
            assert "type" in c
            assert "level" in c


class TestF7P1CustomerMaturity:
    """F7.11 客户成长路径"""

    def test_get_maturity_api(self, client, project):
        resp = client.get(f"/api/v1/projects/{project}/self-service/maturity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assessment = data["result"]["assessment"]
        assert "level" in assessment
        assert assessment["level"] in ["L1", "L2", "L3", "L4"]
        assert "dimensions" in assessment
        assert "growth_path" in assessment

    def test_assess_maturity_with_behavior(self, client, project):
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/maturity/assess",
            json={
                "behavior": {
                    "ai_cognition_score": 70,
                    "requirement_score": 60,
                    "tech_score": 50,
                    "self_service_score": 65,
                }
            },
        )
        assert resp.status_code == 200
        assessment = resp.json()["result"]["assessment"]
        assert assessment["avg_score"] > 50
        assert len(assessment["next_level_recommendations"]) > 0

    def test_maturity_growth_path(self, client, project):
        resp = client.get(f"/api/v1/projects/{project}/self-service/maturity")
        growth_path = resp.json()["result"]["assessment"]["growth_path"]
        assert len(growth_path) == 4
        levels = [g["level"] for g in growth_path]
        assert levels == ["L1", "L2", "L3", "L4"]


class TestF7P1QuoteGeneration:
    """F7.12 付费转化引导"""

    def test_get_quote_api(self, client, project):
        resp = client.get(f"/api/v1/projects/{project}/self-service/quote")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        quote = data["result"]["quote"]
        assert "phased_pricing" in quote
        assert "first_year_total" in quote
        assert "conversion_strategy" in quote
        assert "next_best_action" in quote

    def test_phased_pricing_structure(self, client, project):
        resp = client.get(f"/api/v1/projects/{project}/self-service/quote")
        phases = resp.json()["result"]["quote"]["phased_pricing"]
        assert len(phases) == 3
        phase_names = [p["phase"] for p in phases]
        assert "POC验证期" in phase_names
        assert "MVP开发期" in phase_names
        assert "运营优化期" in phase_names

    def test_quote_roi(self, client, project):
        resp = client.get(f"/api/v1/projects/{project}/self-service/quote")
        quote = resp.json()["result"]["quote"]
        assert quote["roi_payback_months"] > 0
        assert quote["first_year_total"] > 0


class TestF7P1Communication:
    """F7.13 客户沟通通道"""

    def test_log_communication_api(self, client, project):
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/communications",
            json={
                "type": "meeting",
                "content": "客户对原型表示满意，希望增加导出功能",
                "participants": ["客户A", "FDE工程师B"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        result = data["result"]
        assert "communication_id" in result
        assert "summary" in result
        assert "action_items" in result["summary"]
        assert len(result["summary"]["action_items"]) > 0

    def test_communication_action_items(self, client, project):
        resp = client.post(
            f"/api/v1/projects/{project}/self-service/communications", json={"type": "call", "content": "讨论部署方案"}
        )
        action_items = resp.json()["result"]["summary"]["action_items"]
        for item in action_items:
            assert "item" in item
            assert "owner" in item
            assert "priority" in item


# ============================================================
# F8 培训模块测试
# ============================================================


class TestF8CompetencyModel:
    """F8.1 FDE能力模型定义"""

    def test_get_competency_model_api(self, client):
        resp = client.get("/api/v1/training/competency-model")
        assert resp.status_code == 200
        model = resp.json()["model"]
        assert "model" in model
        assert "levels" in model
        assert "knowledge" in model["model"]
        assert "skill" in model["model"]
        assert "experience" in model["model"]

    def test_competency_model_dimensions(self, training_agent):
        result = training_agent._get_competency_model()
        model = result.structured_output["model"]
        assert len(model) == 3
        assert model["knowledge"]["name"].startswith("知识")
        assert model["skill"]["name"].startswith("技能")
        assert model["experience"]["name"].startswith("经验")

    def test_competency_model_levels(self, training_agent):
        result = training_agent._get_competency_model()
        levels = result.structured_output["levels"]
        assert len(levels) == 5
        assert "L1" in levels
        assert levels["L3"]["name"] == "合格FDE"
        assert levels["L5"]["name"] == "专家FDE"

    def test_total_competencies(self, training_agent):
        result = training_agent._get_competency_model()
        assert result.structured_output["total_competencies"] == 15  # 5+6+4


class TestF8CompetencyAssessment:
    """F8.1+F8.7 能力评估"""

    def test_assess_api(self, client):
        resp = client.post(
            "/api/v1/training/assess", json={"background": {"ai_experience_years": 1, "dev_experience_years": 3}}
        )
        assert resp.status_code == 200
        assessment = resp.json()["assessment"]
        assert "overall_level" in assessment
        assert "avg_score" in assessment
        assert "dimension_scores" in assessment
        assert "strengths" in assessment
        assert "weaknesses" in assessment

    def test_assess_with_experience(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "assess_competency",
                    "background": {"ai_experience_years": 2, "dev_experience_years": 5, "fde_experience": True},
                }
            )
        )
        assert result.success
        assert result.structured_output["avg_score"] > 30
        assert result.structured_output["overall_level"] in ["L2", "L3", "L4"]

    def test_assess_beginner(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "assess_competency",
                    "background": {"ai_experience_years": 0, "dev_experience_years": 0},
                }
            )
        )
        assert result.success
        assert result.structured_output["overall_level"] == "L1"


class TestF8LearningPath:
    """F8.2 个性化学习路径生成"""

    def test_generate_path_api(self, client):
        resp = client.post("/api/v1/training/learning-path", json={"target_level": "L3", "current_level": "L1"})
        assert resp.status_code == 200
        path = resp.json()["learning_path"]
        assert "path" in path
        assert "weekly_plan" in path
        assert len(path["weekly_plan"]) == 6
        assert path["path"]["duration_weeks"] == 6

    def test_weekly_plan_structure(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "generate_learning_path",
                    "target_level": "L3",
                }
            )
        )
        weeks = result.structured_output["weekly_plan"]
        assert weeks[0]["theme"] == "基础认知"
        assert weeks[1]["theme"] == "调研分析实战"
        assert weeks[5]["theme"] == "综合实战与认证"
        for week in weeks:
            assert "topics" in week
            assert "practical_tasks" in week
            assert "assessment" in week

    def test_estimated_effort(self, client):
        resp = client.post("/api/v1/training/learning-path", json={"target_level": "L3"})
        assert resp.json()["learning_path"]["estimated_effort_hours"] > 100


class TestF8AICoach:
    """F8.3 AI教练对话辅导"""

    def test_coach_chat_api(self, client):
        resp = client.post("/api/v1/training/coach/chat", json={"message": "如何做需求分析？", "learner_id": "test"})
        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert "reply" in reply
        assert len(reply["reply"]["answer"]) > 10
        assert "related_resources" in reply
        assert "suggested_next_steps" in reply

    def test_coach_error_handling(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "coach_chat",
                    "message": "代码报错了怎么办？",
                }
            )
        )
        assert result.success
        assert (
            "排查" in result.structured_output["reply"]["answer"]
            or "错误" in result.structured_output["reply"]["answer"]
        )

    def test_coach_socratic_style(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "coach_chat",
                    "message": "怎么做方案设计？",
                }
            )
        )
        answer = result.structured_output["reply"]["answer"]
        # 苏格拉底式：包含提问引导
        assert "？" in answer or "分析" in answer


class TestF8Sandbox:
    """F8.4 实战演练沙箱"""

    def test_start_sandbox_api(self, client):
        resp = client.post("/api/v1/training/sandbox/start", json={"scenario": "research", "difficulty": "beginner"})
        assert resp.status_code == 200
        sandbox = resp.json()["sandbox"]["sandbox"]
        assert sandbox["status"] == "ready"
        assert len(sandbox["tasks"]) > 0
        assert sandbox["scenario"] == "research"

    def test_sandbox_full_delivery(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "start_sandbox",
                    "scenario": "full_delivery",
                }
            )
        )
        assert result.success
        tasks = result.structured_output["sandbox"]["tasks"]
        assert len(tasks) == 6  # 完整交付6个任务

    def test_submit_sandbox_work(self, client):
        # 先启动沙箱
        resp = client.post("/api/v1/training/sandbox/start", json={"scenario": "design"})
        sandbox_id = resp.json()["sandbox"]["sandbox"]["sandbox_id"]
        task_id = resp.json()["sandbox"]["sandbox"]["tasks"][0]["id"]
        # 提交作业
        resp = client.post(
            "/api/v1/training/sandbox/submit",
            json={
                "sandbox_id": sandbox_id,
                "task_id": task_id,
                "work": "这是我的方案设计作业，包含产品方案和技术方案...",
            },
        )
        assert resp.status_code == 200
        feedback = resp.json()["feedback"]
        assert "score" in feedback["feedback"]
        assert 0 <= feedback["feedback"]["score"] <= 100
        assert "passed" in feedback
        assert "coach_comment" in feedback["feedback"]


class TestF8KnowledgeBase:
    """F8.6 FDE知识库与案例库"""

    def test_search_knowledge_api(self, client):
        resp = client.get("/api/v1/training/knowledge/search?query=RAG")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results["total"] > 0
        assert len(results["results"]) > 0

    def test_search_by_category(self, client):
        resp = client.get("/api/v1/training/knowledge/search?query=方案&category=solution_design")
        assert resp.status_code == 200
        results = resp.json()["results"]["results"]
        for r in results:
            assert r["category"] == "solution_design"

    def test_knowledge_structure(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "search_knowledge",
                    "query": "Badcase",
                }
            )
        )
        results = result.structured_output["results"]
        for r in results:
            assert "title" in r
            assert "category" in r
            assert "difficulty" in r
            assert "tags" in r


class TestF8ExamCertification:
    """F8.7 能力评估与认证"""

    def test_take_exam_api(self, client):
        resp = client.post("/api/v1/training/exam", json={"target_level": "L3", "learner_id": "exam-test"})
        assert resp.status_code == 200
        exam = resp.json()["exam_result"]
        assert "total_score" in exam
        assert "passed" in exam
        assert "sections" in exam
        assert len(exam["sections"]) == 3

    def test_exam_sections(self, training_agent):
        import asyncio

        result = asyncio.run(
            training_agent.run(
                {
                    "task_type": "take_exam",
                    "target_level": "L3",
                }
            )
        )
        sections = result.structured_output["sections"]
        section_names = [s["name"] for s in sections]
        assert "理论知识" in section_names
        assert "实操能力" in section_names
        assert "案例分析" in section_names

    def test_certification_after_pass(self, training_agent):
        import asyncio

        # 多次考核直到通过（mock评分通常70-85分，L3阈值70）
        for _ in range(3):
            result = asyncio.run(
                training_agent.run(
                    {
                        "task_type": "take_exam",
                        "target_level": "L3",
                    }
                )
            )
            if result.structured_output["passed"]:
                assert "certification" in result.structured_output
                cert = result.structured_output["certification"]
                assert cert["level"] == "L3"
                assert "cert_id" in cert
                assert "issued_at" in cert
                break

    def test_get_certifications_api(self, client):
        resp = client.get("/api/v1/training/certifications?learner_id=exam-test")
        assert resp.status_code == 200
        assert "certifications" in resp.json()


class TestF8EndToEnd:
    """F8培训模块端到端流程：评估→学习路径→教练→沙箱→考核→认证"""

    def test_full_training_journey(self, client):
        learner_id = "journey-test"

        # 1. 能力评估
        resp = client.post(
            "/api/v1/training/assess",
            json={
                "learner_id": learner_id,
                "background": {"ai_experience_years": 0, "dev_experience_years": 0},
            },
        )
        assert resp.status_code == 200
        level = resp.json()["assessment"]["overall_level"]
        assert level in ["L1", "L2"]  # 零基础应为L1，边界可能L2

        # 2. 生成学习路径
        resp = client.post(
            "/api/v1/training/learning-path",
            json={
                "learner_id": learner_id,
                "target_level": "L3",
                "current_level": "L1",
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()["learning_path"]["weekly_plan"]) == 6

        # 3. AI教练对话
        resp = client.post(
            "/api/v1/training/coach/chat",
            json={
                "learner_id": learner_id,
                "message": "RAG是什么？",
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()["reply"]["reply"]["answer"]) > 10

        # 4. 启动沙箱
        resp = client.post(
            "/api/v1/training/sandbox/start",
            json={
                "learner_id": learner_id,
                "scenario": "research",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sandbox"]["sandbox"]["status"] == "ready"

        # 5. 搜索知识库
        resp = client.get(f"/api/v1/training/knowledge/search?query=RAG&learner_id={learner_id}")
        assert resp.status_code == 200
        assert resp.json()["results"]["total"] > 0

        # 6. 参加考核
        resp = client.post(
            "/api/v1/training/exam",
            json={
                "learner_id": learner_id,
                "target_level": "L3",
            },
        )
        assert resp.status_code == 200
        assert "total_score" in resp.json()["exam_result"]

        print("F8完整培训旅程验证通过")
