"""本体模块测试（v0.4-b：store 增量 merge / extractor Mock / gateway / 独立服务 / 引擎 API）。

验收对齐 13 号 §五 b 行：多文档实体≥20/关系≥15；增量不重复计数；图可渲染（Mermaid）。
"""

from __future__ import annotations

import httpx
import pytest

from src.ontology.extractor import _mock_derive, extract_ontology
from src.ontology.gateway import (
    EmbeddedOntologyGateway,
    FallbackOntologyGateway,
    RemoteOntologyGateway,
    get_ontology_gateway,
    reset_ontology_gateway,
)
from src.ontology.store import EmbeddedOntologyStore
from src.ontology.types import Entity, OntologyError, Relation


def make_batch(title: str = "验收测试文档"):
    """Mock 派生一批三列表（含 doc_ref 空载体）。"""
    ents, rels, rules = _mock_derive(title, "来料检验IQC 与 MES检验记录 相关内容")
    return ents, rels, rules


# ---------------------------------------------------------------- Store
class TestStore:
    def test_merge_idempotent_and_no_dup_count(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        ents, rels, rules = make_batch("文档A")
        r1 = store.upsert_batch("p1", ents, rels, rules, doc_ref="doc-a")
        assert r1.entities_added >= 20 and r1.relations_added >= 15 and r1.rules_added >= 3

        # 同一批重推（模拟重抽）：不新增（增量不重复计数验收）
        r2 = store.upsert_batch("p1", ents, rels, rules, doc_ref="doc-a")
        assert r2.entities_added == 0 and r2.relations_added == 0 and r2.rules_added == 0
        graph = store.get_graph("p1")
        assert graph.to_payload()["stats"]["entities"] == len(ents)
        assert graph.to_payload()["stats"]["relations"] == len(rels)

    def test_incremental_multi_doc_accumulates(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        for i, title in enumerate(["方案书", "工单记录", "SOP手册"]):
            ents, rels, rules = make_batch(title)
            store.upsert_batch("p1", ents, rels, rules, doc_ref=f"doc-{i}")
        stats = store.get_graph("p1").to_payload()["stats"]
        assert stats["entities"] >= 20 and stats["relations"] >= 15  # roadmap 验收
        assert stats["entities"] >= 20 + 3  # 3 个标题派生项目实体累积
        assert store.stats("p1")["extracted_docs"] == 3

    def test_property_merge_and_source_dedup(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        ent = Entity(
            id=Entity.make_id("流程节点", "来料检验IQC"),
            type="流程节点",
            name="来料检验IQC",
            properties={"频率": "每批"},
        )
        store.upsert_batch("p1", [ent], [], [], doc_ref="d1")
        ent2 = Entity(
            id=ent.id, type="流程节点", name="来料检验IQC", properties={"频率": "每批", "责任人": "质量工程师"}
        )
        store.upsert_batch("p1", [ent2], [], [], doc_ref="d2")
        found = store.find_entities("p1", "IQC")
        assert len(found) == 1
        assert found[0].properties == {"频率": "每批", "责任人": "质量工程师"}
        assert found[0].source_docs == ["d1", "d2"]

    def test_orphan_relations_skipped(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        a = Entity(id=Entity.make_id("系统", "ERP系统"), type="系统", name="ERP系统")
        ghost = Relation(a.id, Entity.make_id("系统", "不存在系统"), "依赖")
        report = store.upsert_batch("p1", [a], [ghost], [], doc_ref="d1")
        assert report.skipped_orphan_relations == 1
        assert store.get_graph("p1").to_payload()["stats"]["relations"] == 0

    def test_soft_delete_not_revived(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        ent = Entity(id=Entity.make_id("流程节点", "过程检验IPQC"), type="流程节点", name="过程检验IPQC")
        store.upsert_batch("p1", [ent], [], [], doc_ref="d1")
        assert store.delete_entity("p1", ent.id) is True
        assert store.delete_entity("p1", ent.id) is False  # 幂等：二次删 404
        assert store.find_entities("p1", "IPQC") == []
        # 后续抽取再遇同名实体：不复活（人工删除权威）
        report = store.upsert_batch("p1", [ent], [], [], doc_ref="d2")
        assert report.skipped_deleted_entities == 1
        assert store.find_entities("p1", "IPQC") == []

    def test_mermaid_and_summary(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        ents, rels, rules = make_batch("文档A")
        store.upsert_batch("p1", ents, rels, rules, doc_ref="d1")
        mermaid = store.get_mermaid("p1")
        assert mermaid.startswith("graph LR")
        assert mermaid.count("-->") == len(rels)
        summary = store.get_summary("p1")
        assert "实体" in summary and "规则" in summary and "IQC" in summary
        assert store.get_summary("empty") == "（本体为空：尚未抽取）"

    def test_annotate_hints(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        ents, rels, rules = make_batch("文档A")
        store.upsert_batch("p1", ents, rels, rules, doc_ref="d1")
        hints = store.annotate_hints("p1", "本批次需执行来料检验IQC，记录写入MES检验记录", "标题")
        assert "来料检验IQC" in hints and "MES检验记录" in hints
        assert store.annotate_hints("p1", "完全无关的内容", "") == []

    def test_extracted_doc_bookkeeping(self, tmp_path):
        store = EmbeddedOntologyStore(str(tmp_path / "o.db"))
        store.mark_extracted("p1", "d1")
        assert store.is_extracted("p1", "d1") is True
        assert store.is_extracted("p1", "d2") is False


# ---------------------------------------------------------------- Extractor
class TestExtractor:
    async def test_mock_meets_acceptance(self):
        ents, rels, rules, mode = await extract_ontology("验收文档", "内容")
        assert mode == "mock"
        assert len(ents) >= 20 and len(rels) >= 15 and len(rules) >= 3

    async def test_mock_stable_ids(self):
        e1, r1, _, _ = await extract_ontology("同一标题", "x")
        e2, _, _, _ = await extract_ontology("同一标题", "y")
        assert {e.id for e in e1} == {e.id for e in e2}

    async def test_title_derived_project_entity(self):
        ents, _, _, _ = await extract_ontology("某汽车零部件产线", "x")
        assert any(e.type == "项目" and "某汽车零部件产线" in e.name for e in ents)


# ---------------------------------------------------------------- Gateway
class TestGateway:
    def test_factory_default_embedded(self):
        reset_ontology_gateway()
        gw = get_ontology_gateway()
        assert isinstance(gw, EmbeddedOntologyGateway)
        assert gw.health()["service"] == "ontology"

    def test_remote_extract_and_errors(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/extract":
                return httpx.Response(200, json={"doc_ref": "d1", "entities_added": 21})
            if request.url.path == "/graph":
                return httpx.Response(500, text="boom")
            if request.url.path == "/entities/zzz":
                return httpx.Response(404, json={"error": {"code": "not_found", "message": "无"}})
            if request.url.path == "/extract2":
                return httpx.Response(503, text="down")
            return httpx.Response(500, text="boom")

        remote = RemoteOntologyGateway("http://test")
        remote._http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler), trust_env=False)
        import asyncio

        report = asyncio.run(remote.extract_and_merge("p1", "t", "c", doc_ref="d1"))
        assert report["entities_added"] == 21
        with pytest.raises(OntologyError) as ei:
            remote.delete_entity("p1", "zzz")
        assert ei.value.code == "not_found"
        from src.ontology.types import OntologyServiceError

        with pytest.raises(OntologyServiceError):
            remote.get_graph("p1")  # handler 对 /graph 返回 200 json；用 /stats 打 5xx

    def test_fallback_degrades_on_service_error(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="down")

        remote = RemoteOntologyGateway("http://test")
        remote._http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler), trust_env=False)
        embedded = EmbeddedOntologyGateway(str(tmp_path / "emb.db"))
        fb = FallbackOntologyGateway(remote, embedded)
        assert fb.degraded_since is None
        stats = fb.stats("p1")  # Remote 5xx → 降级 Embedded 正常返回
        assert stats["entities"] == 0
        assert fb.degraded_since is not None

        # 契约错误（4xx）不降级
        def handler_404(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": {"code": "not_found", "message": "x"}})

        remote._http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler_404), trust_env=False)
        with pytest.raises(OntologyError):
            fb.delete_entity("p1", "zzz")


# ---------------------------------------------------------------- 独立服务（契约 20 号）
class TestStandaloneServer:
    @pytest.fixture()
    def client(self, tmp_path):
        from fastapi.testclient import TestClient

        from src.ontology.server import create_app

        gw = EmbeddedOntologyGateway(str(tmp_path / "svc.db"))
        with TestClient(create_app(gw, token="")) as c:
            yield c, gw

    def test_full_loop(self, client):
        c, _ = client
        assert c.get("/health").json()["service"] == "ontology"
        r = c.post(
            "/extract",
            json={"title": "验收文档", "content": "IQC 来料检验流程…", "doc_ref": "d1"},
            headers={"X-Onto-Project": "p1"},
        )
        assert r.status_code == 200 and r.json()["entities_added"] >= 20
        graph = c.get("/graph", headers={"X-Onto-Project": "p1"}).json()
        assert graph["stats"]["entities"] >= 20
        mermaid = c.get("/mermaid", headers={"X-Onto-Project": "p1"})
        assert mermaid.text.startswith("graph LR")
        hints = c.post("/hints", json={"content": "执行来料检验IQC"}, headers={"X-Onto-Project": "p1"}).json()["hints"]
        assert "来料检验IQC" in hints
        ent_id = graph["entities"][0]["id"]
        assert c.delete(f"/entities/{ent_id}", headers={"X-Onto-Project": "p1"}).json()["deleted"]
        assert c.delete(f"/entities/{ent_id}", headers={"X-Onto-Project": "p1"}).status_code == 404

    def test_validation_and_401(self, tmp_path):
        from fastapi.testclient import TestClient

        from src.ontology.server import create_app

        gw = EmbeddedOntologyGateway(str(tmp_path / "svc2.db"))
        with TestClient(create_app(gw, token="secret")) as c:
            assert c.get("/health").status_code == 200  # /health 不鉴权
            assert c.get("/graph").status_code == 401
            ok = {"Authorization": "Bearer secret", "X-Onto-Project": "p1"}
            assert c.post("/extract", json={"content": ""}, headers=ok).status_code == 400
            assert c.get("/graph", headers=ok).status_code == 200


# ---------------------------------------------------------------- 引擎侧 API
@pytest.fixture()
def api_client():
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def project(api_client):
    resp = api_client.post("/api/v1/projects", json={"name": "onto-api-test"})
    assert resp.status_code == 200, resp.text
    return resp.json()["project"]


def _upload_doc(api_client, project_id, filename, content):

    files = {"file": (filename, content.encode("utf-8"), "text/markdown")}
    resp = api_client.post(f"/api/v1/projects/{project_id}/documents", files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestOntologyAPI:
    def test_extract_graph_mermaid_delete_loop(self, api_client, project):
        pid = project["id"]
        _upload_doc(
            api_client,
            pid,
            "质量手册.txt",
            "第一章 来料检验IQC\n来料检验IQC 负责物料入库质量，记录写入 MES检验记录。第二章 不合格品评审MRB",
        )
        r = api_client.post(f"/api/v1/projects/{pid}/ontology/extract", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["extracted"] >= 1 and body["totals"]["entities_added"] >= 20
        graph = api_client.get(f"/api/v1/projects/{pid}/ontology").json()
        assert graph["stats"]["entities"] >= 20 and graph["stats"]["relations"] >= 15
        mermaid = api_client.get(f"/api/v1/projects/{pid}/ontology/mermaid")
        assert mermaid.text.startswith("graph LR")
        summary = api_client.get(f"/api/v1/projects/{pid}/ontology/summary").json()["summary"]
        assert "IQC" in summary
        # 重抽幂等：第二次 extract 跳过已抽取文档（doc_ref 记账）
        r2 = api_client.post(f"/api/v1/projects/{pid}/ontology/extract", json={})
        assert r2.json()["skipped_already_extracted"] >= 1
        # 人工删除软删 + 实体检索过滤
        ent = api_client.get(f"/api/v1/projects/{pid}/ontology/entities", params={"q": "IPQC"}).json()["entities"]
        assert ent, "应能按关键字找到 IPQC 实体"
        del_r = api_client.delete(f"/api/v1/projects/{pid}/ontology/entities/{ent[0]['id']}")
        assert del_r.status_code == 200
        assert (
            api_client.get(f"/api/v1/projects/{pid}/ontology/entities", params={"q": "IPQC"}).json()["entities"] == []
        )

    def test_extract_force_and_project_404(self, api_client, project):
        pid = project["id"]
        _upload_doc(api_client, pid, "另一份.txt", "OQC 成品检验 出货检验 流程说明")
        r = api_client.post(f"/api/v1/projects/{pid}/ontology/extract", json={"force": True})
        assert r.status_code == 200 and r.json()["extracted"] >= 1
        assert api_client.post("/api/v1/projects/no-such/ontology/extract", json={}).status_code == 404
        assert api_client.get("/api/v1/projects/no-such/ontology").status_code == 404

    def test_entity_hints_backfill_into_kb_ingest(self, api_client, project):
        """本体抽取后，知识库 ingest 的 metadata.entity_hints 应被预标注填充（pipeline 回填）。"""
        from src.knowledge.pipeline import doc_record_to_spec

        pid = project["id"]
        _upload_doc(api_client, pid, "本体联动.txt", "来料检验IQC 流程与 MES检验记录 说明")
        r = api_client.post(f"/api/v1/projects/{pid}/ontology/extract", json={})
        assert r.status_code == 200
        spec = doc_record_to_spec(
            {"id": "doc-x", "filename": "新文档.txt", "content": "新文档提及 来料检验IQC 环节"},
            project_id=pid,
        )
        assert "来料检验IQC" in spec.metadata["entity_hints"]
        # 无项目上下文（旧行为兼容）：留空不报错
        spec2 = doc_record_to_spec({"id": "doc-y", "content": "x"})
        assert spec2.metadata["entity_hints"] == []
