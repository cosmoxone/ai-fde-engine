"""
B4 可编辑确认流测试：需求/功能项编辑 → 进入基线 → 可导出
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _run_and_wait(client: TestClient, url: str, body: dict | None = None):
    tid = client.post(url, json=body or {}).json()["task_id"]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        time.sleep(0.05)
    return t


def _project_with_baseline(client: TestClient) -> str:
    pid = client.post("/api/v1/projects", json={"name": "编辑流验证", "industry": "制造业"}).json()["project"]["id"]
    t = _run_and_wait(client, f"/api/v1/projects/{pid}/research/run", {"client_requirements": "质检知识库"})
    assert t["status"] == "completed"
    return pid


class TestRequirementEdit:
    def test_edit_enters_baseline_and_export(self, client: TestClient):
        pid = _project_with_baseline(client)
        project = client.get(f"/api/v1/projects/{pid}").json()["project"]
        r1 = project["requirements_baseline"]["requirements"]["functional"][0]

        resp = client.patch(
            f"/api/v1/projects/{pid}/requirements/{r1['id']}",
            json={
                "title": "人工修订后的标题",
                "acceptance_criteria": "准确率≥97%，响应≤2秒（客户2026标准）",
                "priority": "P0",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["requirement"]["title"] == "人工修订后的标题"

        # 修改进入基线
        project = client.get(f"/api/v1/projects/{pid}").json()["project"]
        r1_new = project["requirements_baseline"]["requirements"]["functional"][0]
        assert r1_new["title"] == "人工修订后的标题"
        assert "97%" in r1_new["acceptance_criteria"]

        # 导出包含修改后内容（B4验收：修改进入基线并导出）
        md = client.get(f"/api/v1/projects/{pid}/export", params={"item": "02-需求基线"}).text
        assert "人工修订后的标题" in md
        assert "97%" in md

    def test_partial_update_keeps_other_fields(self, client: TestClient):
        pid = _project_with_baseline(client)
        r1 = client.get(f"/api/v1/projects/{pid}").json()["project"]["requirements_baseline"]["requirements"][
            "functional"
        ][0]
        original_desc = r1["description"]

        resp = client.patch(f"/api/v1/projects/{pid}/requirements/{r1['id']}", json={"priority": "P2"})
        assert resp.status_code == 200
        assert resp.json()["requirement"]["priority"] == "P2"
        assert resp.json()["requirement"]["description"] == original_desc  # 未提交字段不变

    def test_invalid_priority_rejected(self, client: TestClient):
        pid = _project_with_baseline(client)
        r1 = client.get(f"/api/v1/projects/{pid}").json()["project"]["requirements_baseline"]["requirements"][
            "functional"
        ][0]
        resp = client.patch(f"/api/v1/projects/{pid}/requirements/{r1['id']}", json={"priority": "P9"})
        assert resp.status_code == 400

    def test_404s(self, client: TestClient):
        pid = client.post("/api/v1/projects", json={"name": "x"}).json()["project"]["id"]
        assert client.patch(f"/api/v1/projects/{pid}/requirements/R99", json={"title": "t"}).status_code == 404
        assert client.patch("/api/v1/projects/nope/requirements/R1", json={}).status_code == 404


class TestFeatureEdit:
    def test_edit_solution_feature(self, client: TestClient):
        pid = _project_with_baseline(client)
        t = _run_and_wait(client, f"/api/v1/projects/{pid}/design/run", {})
        assert t["status"] == "completed"

        project = client.get(f"/api/v1/projects/{pid}").json()["project"]
        f1 = project["solutions"]["product_solution"]["features"][0]

        resp = client.patch(
            f"/api/v1/projects/{pid}/solutions/features/{f1['id']}",
            json={"name": "客户定名功能", "description": "按客户要求调整"},
        )
        assert resp.status_code == 200
        assert resp.json()["feature"]["name"] == "客户定名功能"

        # 导出方案含修改
        md = client.get(f"/api/v1/projects/{pid}/export", params={"item": "03-方案设计"}).text
        assert "客户定名功能" in md

    def test_edit_feature_404(self, client: TestClient):
        pid = _project_with_baseline(client)
        assert client.patch(f"/api/v1/projects/{pid}/solutions/features/F99", json={}).status_code == 404
