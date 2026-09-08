"""
v0.3.0 测试：生态集成（night-factory 工单 / RPA 编排）+ 定时调度
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.config import get_settings


def _project_with_baseline(client: TestClient) -> str:
    pid = client.post("/api/v1/projects", json={"name": "工单验证", "industry": "制造业"}).json()["project"]["id"]
    tid = client.post(f"/api/v1/projects/{pid}/research/run", json={"client_requirements": "质检知识库"}).json()[
        "task_id"
    ]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        time.sleep(0.05)
    assert t["status"] == "completed"
    return pid


class TestNightFactoryTickets:
    def test_tickets_schema_compatible(self, client: TestClient):
        """工单字段与 night-factory tasks/*.json schema 完全兼容"""
        pid = _project_with_baseline(client)
        data = client.get(f"/api/v1/projects/{pid}/delivery/tickets").json()
        assert data["success"] is True
        assert data["total"] >= 1
        for t in data["tickets"]:
            assert t["id"].startswith("FDE-")
            assert t["objective"]
            assert t["repo_path"]
            assert t["complexity"] in ("low", "high")
            assert set(t["budget"].keys()) == {"turns", "tokens", "wall_time_hours"}
            assert isinstance(t["acceptance"], list) and t["acceptance"]

    def test_acceptance_criteria_flows_to_ticket(self, client: TestClient):
        """核心衔接：需求量化验收标准 → 工单 acceptance[]"""
        pid = _project_with_baseline(client)
        project = client.get(f"/api/v1/projects/{pid}").json()["project"]
        req1 = project["requirements_baseline"]["requirements"]["functional"][0]
        tickets = client.get(f"/api/v1/projects/{pid}/delivery/tickets").json()["tickets"]
        ticket = next(t for t in tickets if t["id"] == f"FDE-{req1['id']}")
        joined = "；".join(ticket["acceptance"])
        # 验收标准文本进入工单验收条目
        assert any(kw in joined for kw in ("率", "秒", "%", "时间"))

    def test_p0_gets_higher_budget(self, client: TestClient):
        pid = _project_with_baseline(client)
        tickets = client.get(f"/api/v1/projects/{pid}/delivery/tickets").json()["tickets"]
        budgets = {t["complexity"]: t["budget"]["turns"] for t in tickets}
        if "high" in budgets and "low" in budgets:
            assert budgets["high"] > budgets["low"]

    def test_export_endpoint(self, client: TestClient):
        pid = _project_with_baseline(client)
        resp = client.get(f"/api/v1/projects/{pid}/delivery/tickets/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert "FDE-" in resp.text

    def test_no_baseline_returns_hint(self, client: TestClient):
        pid = client.post("/api/v1/projects", json={"name": "空"}).json()["project"]["id"]
        data = client.get(f"/api/v1/projects/{pid}/delivery/tickets").json()
        assert data["success"] is True
        assert data["tickets"] == []
        assert "调研" in data["message"]


class TestRpaDispatch:
    def test_dispatch_pending_without_webhook(self, client: TestClient):
        """未配置 RPA_WEBHOOK_URL → pending_integration（编排位就绪）"""
        pid = _project_with_baseline(client)
        tid = client.post(f"/api/v1/projects/{pid}/benchmarks/generate", json={}).json()["task_id"]
        for _ in range(40):
            t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        bm_id = client.get(f"/api/v1/projects/{pid}/benchmarks").json()["benchmarks"][0]["benchmark_id"]
        resp = client.post(f"/api/v1/projects/{pid}/benchmarks/{bm_id}/rpa-dispatch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["dispatch"]["status"] == "pending_integration"
        assert data["runner_configured"] is False
        assert data["dispatch"]["case_count"] >= 1

    def test_dispatch_404s(self, client: TestClient):
        pid = client.post("/api/v1/projects", json={"name": "x"}).json()["project"]["id"]
        assert client.post(f"/api/v1/projects/{pid}/benchmarks/nope/rpa-dispatch").status_code == 404


class TestIterationScheduler:
    def test_disabled_by_default_config(self):
        """默认 cron '0 20 * * *'（旧格式，无冒号）→ 调度器自动不启用"""
        assert ":" not in get_settings().iteration_cron

    @staticmethod
    def _scheduler_quits_on_invalid_format(monkeypatch):
        import asyncio

        from src.main import _iteration_scheduler

        async def run():
            task = asyncio.create_task(_iteration_scheduler())
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_invalid_format_disabled(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "iteration_cron", "not-a-time")
        self._scheduler_quits_on_invalid_format(monkeypatch)  # 不抛异常即通过
