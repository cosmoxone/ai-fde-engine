"""
API集成测试
"""

import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(tmp_path):
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    os.environ["OPENHANDS_WORKSPACE_BASE"] = str(tmp_path)
    return TestClient(app)


@pytest.fixture
def test_project(client):
    """创建测试项目"""
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "测试项目",
            "client_name": "测试客户",
            "industry": "制造业",
            "description": "用于API测试的项目",
        },
    )
    return response.json()["project"]


class TestHealthAPI:
    """健康检查API测试"""

    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.2.1"
        assert "services" in data


class TestProjectAPI:
    """项目管理API测试"""

    def test_create_project(self, client):
        response = client.post(
            "/api/v1/projects",
            json={
                "name": "新项目",
                "client_name": "客户A",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["project"]["name"] == "新项目"
        assert "id" in data["project"]

    def test_list_projects(self, client, test_project):
        response = client.get("/api/v1/projects")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_get_project(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["project"]["name"] == "测试项目"
        assert "memory_stats" in data

    def test_get_nonexistent_project(self, client):
        response = client.get("/api/v1/projects/nonexistent-id")
        assert response.status_code == 404


class TestDocumentAPI:
    """文档管理API测试"""

    def test_upload_document(self, client, test_project, tmp_path):
        doc_file = tmp_path / "test.txt"
        doc_file.write_text("测试业务文档内容\n业务流程包括受理、审核、处理。", encoding="utf-8")
        with open(doc_file, "rb") as f:
            response = client.post(
                f"/api/v1/projects/{test_project['id']}/documents",
                files={"file": ("test.txt", f, "text/plain")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["document"]["filename"] == "test.txt"
        assert data["parse_result"]["success"] is True

    def test_list_documents(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/documents")
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data


class TestResearchAPI:
    """调研分析API测试"""

    def test_run_research(self, client, test_project):
        response = client.post(
            f"/api/v1/projects/{test_project['id']}/research/run",
            json={"client_requirements": "需要智能审核助手"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data


class TestDesignAPI:
    """方案设计API测试"""

    def test_run_design(self, client, test_project):
        response = client.post(
            f"/api/v1/projects/{test_project['id']}/design/run",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data


class TestDeliveryAPI:
    """开发交付API测试"""

    def test_run_delivery(self, client, test_project):
        response = client.post(
            f"/api/v1/projects/{test_project['id']}/delivery/run",
            json={"task_type": "generate_code", "project_name": "test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data


class TestBenchmarkAPI:
    """Benchmark API测试"""

    def test_generate_benchmark(self, client, test_project):
        response = client.post(f"/api/v1/projects/{test_project['id']}/benchmarks/generate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data

    def test_list_benchmarks(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/benchmarks")
        assert response.status_code == 200


class TestIterationAPI:
    """夜间迭代API测试"""

    def test_run_iteration(self, client, test_project):
        response = client.post(
            f"/api/v1/projects/{test_project['id']}/iteration/run",
            json={"badcases": [{"id": "B1", "input": "test", "actual_output": "不知道", "severity": "major"}]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "task_id" in data


class TestBadcaseAPI:
    """Badcase API测试"""

    def test_add_badcase(self, client, test_project):
        response = client.post(
            f"/api/v1/projects/{test_project['id']}/badcases",
            json={
                "input": "用户问题",
                "actual_output": "错误回答",
                "expected_output": "正确回答",
                "error_type": "knowledge",
                "severity": "major",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["badcase"]["severity"] == "major"


class TestMemoryAPI:
    """记忆API测试"""

    def test_search_memory(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/memory/search?query=项目&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "results" in data

    def test_memory_stats(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/memory/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "stats" in data

    def test_consolidate_memory(self, client, test_project):
        response = client.post(f"/api/v1/projects/{test_project['id']}/memory/consolidate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "result" in data


class TestTaskAPI:
    """任务API测试"""

    def test_get_task(self, client, test_project):
        # 先创建一个任务
        run_resp = client.post(
            f"/api/v1/projects/{test_project['id']}/research/run",
            json={},
        )
        task_id = run_resp.json()["task_id"]
        response = client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["task"]["id"] == task_id

    def test_get_nonexistent_task(self, client):
        response = client.get("/api/v1/tasks/nonexistent")
        assert response.status_code == 404

    def test_list_project_tasks(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data


class TestProgressAPI:
    """项目进度API测试"""

    def test_project_progress(self, client, test_project):
        response = client.get(f"/api/v1/projects/{test_project['id']}/progress")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "status" in data
        assert "progress" in data
        assert "documents_count" in data
