"""
B5 测试：Badcase 持久化 + 修复建议闭环
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agents.delivery import DeliveryAgent
from src.pipeline.iteration import NightlyIterationPipeline
from src.storage.memory import MemoryStorage


class TestBadcaseStorage:
    def test_add_list_filter(self):
        s = MemoryStorage()
        s.add_badcase({"id": "b1", "project_id": "p1", "status": "open", "input": "q1"})
        s.add_badcase({"id": "b2", "project_id": "p1", "status": "processed", "input": "q2"})
        assert len(s.list_badcases("p1")) == 2
        assert len(s.list_badcases("p1", status="open")) == 1
        assert s.get_badcase("b1")["input"] == "q1"
        assert s.get_badcase("nope") is None

    def test_update_status(self):
        s = MemoryStorage()
        s.add_badcase({"id": "b1", "status": "open"})
        updated = s.update_badcase("b1", {"status": "processed", "processed_version": "v0.1.3"})
        assert updated["status"] == "processed"
        assert s.list_badcases(status="open") == []


class TestFixSuggestions:
    def test_suggest_fix_rule_conflict(self):
        agent = DeliveryAgent("suggest-test")
        bc = {"input": "能否特采放行", "actual_output": "可以放行", "expected_output": "需MRB评审"}
        sug = agent._suggest_fix(bc, {"type": "rule", "reason": "业务规则理解偏差"})
        assert sug["type"] == "rule_confirmation"
        assert "业务规则确认" in sug["action"]
        assert "特采放行" in sug["draft"]

    def test_suggest_fix_model_boundary(self):
        agent = DeliveryAgent("suggest-test")
        bc = {"input": "预测明年销售", "actual_output": "不知道", "expected_output": "无法预测"}
        sug = agent._suggest_fix(bc, {"type": "model_boundary", "reason": "能力边界"})
        assert sug["type"] == "known_limitation"
        assert "拒答" in sug["draft"]

    @pytest.mark.asyncio
    async def test_pipeline_emits_suggestions(self):
        """夜间迭代：不可自动修复的badcase → 输出建议而非仅标记"""
        pipeline = NightlyIterationPipeline("sug-pipeline")
        badcases = [
            {
                "id": "bc-rule",
                "input": "规则冲突问题特采放行吗",
                "actual_output": "可以",
                "expected_output": "走MRB",
                "error_type": "rule",
            },
            {
                "id": "bc-knowledge",
                "input": "不知道标准是什么",
                "actual_output": "未找到",
                "expected_output": "标准A",
            },
        ]
        result = await pipeline.run(badcases, [])
        assert result.need_human >= 1
        assert len(result.fix_suggestions) >= 1
        assert result.fix_suggestions[0]["action"]
        assert "修复建议" in result.report


class TestBadcaseAPIFlow:
    def test_submit_and_auto_collect(self, client: TestClient):
        """提交badcase入库 → 不带badcases触发迭代 → 自动归集并标记processed"""
        pid = client.post("/api/v1/projects", json={"name": "闭环验证"}).json()["project"]["id"]

        # 提交两条
        for i in range(2):
            resp = client.post(
                f"/api/v1/projects/{pid}/badcases",
                json={"input": f"问题{i}", "actual_output": "错", "expected_output": "对", "error_type": "knowledge"},
            )
            assert resp.status_code == 200

        # 列表
        data = client.get(f"/api/v1/projects/{pid}/badcases").json()
        assert data["total"] == 2
        assert all(b["status"] == "open" for b in data["badcases"])

        # 触发夜间迭代（不带badcases → 自动归集）
        tid = client.post(f"/api/v1/projects/{pid}/iteration/run", json={"badcases": [], "benchmark_cases": []}).json()[
            "task_id"
        ]
        import time

        for _ in range(60):
            t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        assert t["status"] == "completed"
        assert t["result"]["badcases_processed"] == 2 or t["result"].get("auto_fixed", 0) >= 1

        # 已处理标记
        data = client.get(f"/api/v1/projects/{pid}/badcases").json()
        assert all(b["status"] == "processed" for b in data["badcases"])

    def test_iteration_result_contains_suggestions(self, client: TestClient):
        pid = client.post("/api/v1/projects", json={"name": "建议验证", "industry": "制造业"}).json()["project"]["id"]
        tid = client.post(
            f"/api/v1/projects/{pid}/iteration/run",
            json={
                "badcases": [
                    {
                        "id": "bc1",
                        "input": "特采放行规则冲突",
                        "actual_output": "可以放行",
                        "expected_output": "需MRB评审",
                        "error_type": "rule",
                    }
                ],
                "benchmark_cases": [],
            },
        ).json()["task_id"]
        import time

        for _ in range(60):
            t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        assert t["status"] == "completed"
        assert isinstance(t["result"].get("fix_suggestions"), list)
