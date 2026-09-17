"""知识库引擎侧 API 测试（v0.4-a 接线：上传自动 ingest + Dashboard 端点）。

覆盖 13 号 §3.4 设计的引擎面端点 + 上传管线挂钩（kb_status 不阻断语义）。
契约面（spec14 HTTP）见 tests/contract/；网关单测见 tests/test_knowledge.py。
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture()
def api_client():
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project(api_client):
    resp = api_client.post("/api/v1/projects", json={"name": "kb-api-test"})
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


MARKER = "ZZAPI" + uuid.uuid4().hex[:8].upper()


def _upload(api_client, project_id, filename="质检手册.md"):
    content = (
        f"# 特采管理\n\n{MARKER} 让步放行需取得客户书面特采许可,经MRB评审,"
        f"放行后记录追溯。\n\n# 记录\n\n特采编号规则参照客户工程规范执行。"
    )
    resp = api_client.post(
        f"/api/v1/projects/{project_id}/documents", files={"file": (filename, content.encode("utf-8"), "text/markdown")}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestUploadAutoIngest:
    def test_upload_ingests_and_reports_status(self, api_client, project):
        data = _upload(api_client, project["id"])
        assert data["success"] is True
        assert data["document"]["kb_status"] == "ingested", "上传后应自动入知识库"

    def test_kb_stats_and_search_after_upload(self, api_client, project):
        _upload(api_client, project["id"])
        stats = api_client.get(f"/api/v1/projects/{project['id']}/kb/stats").json()
        assert stats["success"] is True
        assert stats["stats"]["documents"] == 1
        assert stats["stats"]["parsing"] == 0

        search = api_client.get(f"/api/v1/projects/{project['id']}/kb/search", params={"q": MARKER, "k": 5}).json()
        assert search["success"] is True
        hits = search["hits"]
        assert hits, "上传并入库后必须能检索命中"
        assert hits[0]["source"]["filename"] == "质检手册.md", "溯源五字段随命中返回"

    def test_rebuild_idempotent(self, api_client, project):
        _upload(api_client, project["id"])
        r1 = api_client.post(f"/api/v1/projects/{project['id']}/kb/ingest").json()
        assert r1["accepted"] == 0 and r1["deduped"] == 1, "重推按 doc_id 幂等去重"

    def test_kb_search_requires_query(self, api_client, project):
        resp = api_client.get(f"/api/v1/projects/{project['id']}/kb/search")
        assert resp.status_code == 422  # FastAPI 必填参数校验

    def test_kb_project_not_found(self, api_client):
        assert api_client.get("/api/v1/projects/p-none/kb/stats").status_code == 404


class TestPendingQueueDashboard:
    def test_curate_queue_confirm_flow(self, api_client, project):
        """夜间迭代产草稿（模拟）→ Dashboard 队列 → confirm → 检索命中 curated"""
        from src.knowledge import EntrySpec, get_knowledge_gateway

        entry = EntrySpec(
            question_pattern=f"{MARKER} 光洁度不达标但尺寸合格能否放行?",
            answer=f"{MARKER} 不能直接放行。需提交MRB评审,取得客户书面特采许可。",
            origin=f"badcase:{MARKER}",
            suggested_by="test",
        )
        entry_id, status = get_knowledge_gateway().curate(project["id"], entry)
        assert status == "pending"

        queue = api_client.get("/api/v1/kb/entries", params={"project_id": project["id"]}).json()
        assert queue["total"] >= 1
        assert any(e["entry_id"] == entry_id for e in queue["entries"])

        r = api_client.post(
            f"/api/v1/kb/entries/{entry_id}/confirm",
            params={"project_id": project["id"]},
            json={"answer": entry.answer + "(终稿)"},
        )
        assert r.json()["status"] == "confirmed"
        # 幂等
        assert (
            api_client.post(f"/api/v1/kb/entries/{entry_id}/confirm", params={"project_id": project["id"]}).json()[
                "status"
            ]
            == "confirmed"
        )
        hits = api_client.get(f"/api/v1/projects/{project['id']}/kb/search", params={"q": MARKER, "k": 10}).json()[
            "hits"
        ]
        assert any(h["entry_type"] == "curated" for h in hits)

    def test_reject_flow(self, api_client, project):
        from src.knowledge import EntrySpec, get_knowledge_gateway

        entry_id, _ = get_knowledge_gateway().curate(
            project["id"],
            EntrySpec(
                question_pattern=f"{MARKER} 拒绝用例问句?",
                answer=f"{MARKER} 拒绝用例答案。",
                origin=f"badcase:{MARKER}-rej",
            ),
        )
        r = api_client.post(
            f"/api/v1/kb/entries/{entry_id}/reject", params={"project_id": project["id"]}, json={"reason": "test"}
        )
        assert r.json()["status"] == "rejected"
        # rejected 不可再 confirm（终态不可逆）
        r2 = api_client.post(f"/api/v1/kb/entries/{entry_id}/confirm", params={"project_id": project["id"]})
        assert r2.status_code == 404
        assert r2.json()["detail"]["code"] == "not_found"

    def test_confirm_nonexistent_404(self, api_client, project):
        r = api_client.post("/api/v1/kb/entries/ke-none/confirm", params={"project_id": project["id"]})
        assert r.status_code == 404
