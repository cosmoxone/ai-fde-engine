"""
D1 经验库测试：全局记忆检索 + 复盘报告
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def _project_with_data(client: TestClient) -> str:
    pid = client.post(
        "/api/v1/projects", json={"name": "经验库验证", "client_name": "客户", "industry": "制造业"}
    ).json()["project"]["id"]
    # 调研（产生记忆+基线）
    tid = client.post(f"/api/v1/projects/{pid}/research/run", json={"client_requirements": "特采放行流程"}).json()[
        "task_id"
    ]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        time.sleep(0.05)
    # badcase
    client.post(
        f"/api/v1/projects/{pid}/badcases",
        json={"input": "特采问题", "actual_output": "错", "expected_output": "对", "error_type": "rule"},
    )
    return pid


class TestGlobalMemorySearch:
    def test_search_across_projects(self, client: TestClient):
        _project_with_data(client)
        _project_with_data(client)

        resp = client.get("/api/v1/memory/global/search", params={"query": "特采"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["projects_searched"] >= 2
        # 结果携带项目名便于识别来源
        for r in data["results"]:
            assert r.get("project_name")

    def test_empty_query_rejected(self, client: TestClient):
        assert client.get("/api/v1/memory/global/search", params={"query": "  "}).status_code == 400


class TestRetrospective:
    def test_retrospective_markdown_sections(self, client: TestClient):
        pid = _project_with_data(client)
        resp = client.get(f"/api/v1/projects/{pid}/retrospective")
        assert resp.status_code == 200
        data = resp.json()
        md = data["markdown"]
        # 五大章节齐备
        for section in ["执行概况", "需求与范围", "质量与 Badcase 处理", "评审与人机协同", "经验沉淀清单"]:
            assert section in md, f"缺章节: {section}"
        # 统计
        s = data["stats"]
        assert s["badcase_total"] == 1
        assert s["task_completed"] >= 1

    def test_retrospective_in_export(self, client: TestClient):
        """复盘进入交付物清单并可导出"""
        pid = _project_with_data(client)
        items = client.get(f"/api/v1/projects/{pid}/export/list").json()["items"]
        assert any(i["key"] == "07-复盘报告" for i in items)

        md = client.get(f"/api/v1/projects/{pid}/export", params={"item": "07-复盘报告"}).text
        assert "经验沉淀清单" in md
        assert "rule" in md  # 复盘含 badcase 类型归因分布

    def test_retrospective_404(self, client: TestClient):
        assert client.get("/api/v1/projects/nope/retrospective").status_code == 404

    def test_empty_project_retro_generates(self, client: TestClient):
        """无任务的项目也能产出基础复盘（零数据容错）"""
        pid = client.post("/api/v1/projects", json={"name": "空复盘"}).json()["project"]["id"]
        resp = client.get(f"/api/v1/projects/{pid}/retrospective")
        assert resp.status_code == 200
        assert "执行概况" in resp.json()["markdown"]
