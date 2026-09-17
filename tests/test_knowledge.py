"""知识库接入层单测（v0.4-a）——Embedded 参考实现即规格,覆盖规格 14 v1.2 主协议语义。

覆盖:
- chunker:偏移边界/顺序/title_path/超长段切分
- Embedded:ingest 幂等、stats 口径、检索溯源五字段、curate 生命周期、附录A
- 工厂:KNOWLEDGE_SERVICE_URL 切换 / Fallback 降级
- KbOsGateway:Envelope 解包/错误映射(MockTransport)
- spec14 参考服务:契约端点全链路 + 鉴权 + 错误分支
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from src.knowledge.chunker import MAX_LEN, chunk_text
from src.knowledge.embedded import EmbeddedKnowledgeGateway
from src.knowledge.gateway import FallbackKnowledgeGateway, reset_knowledge_gateway
from src.knowledge.kbos import KbOsGateway
from src.knowledge.server import create_app
from src.knowledge.types import DocSpec, EntrySpec, KBContractError, KnowledgeGatewayError

MARKER = "ZZTEST" + uuid.uuid4().hex[:8].upper()
PROJECT = "p-test"


def make_doc(idx: int, marker: str = MARKER) -> DocSpec:
    return DocSpec(
        title=f"probe-{marker}-{idx}.md",
        content=f"{marker} 第{idx}条:让步放行需取得客户书面特采许可,经MRB评审,放行后记录追溯。{marker}",
        metadata={
            "doc_id": f"doc-{marker}-{idx}",
            "title_path": "测试>探针",
            "entity_hints": ["特采"],
            "origin": "test",
        },
    )


def make_entry(idx: int, marker: str = MARKER) -> EntrySpec:
    return EntrySpec(
        question_pattern=f"{marker} 光洁度不达标但尺寸合格能否放行?",
        answer=f"{marker} 不能直接放行。需提交MRB评审,取得客户书面特采许可后方可放行。",
        origin=f"badcase:{marker}-{idx}",
        suggested_by="test",
    )


@pytest.fixture()
def gw(tmp_path):
    gateway = EmbeddedKnowledgeGateway(str(tmp_path / "kb.db"))
    yield gateway
    gateway.close()


# ============================================================
# 切块器
# ============================================================


class TestChunker:
    def test_offsets_within_content_and_sequential(self):
        content = (
            "# 第一章 来料检验\n\n"
            + "A类物料按GB/T 2828.1抽样。" * 12
            + "\n\n"
            + "# 第二章 放行\n\n"
            + "让步放行需取得客户书面特采许可,经MRB评审。" * 8
        )
        chunks = chunk_text(content)
        assert 1 < len(chunks) <= 6
        for c in chunks:
            assert 0 <= c.start_at < c.end_at <= len(content), "偏移必须在原文范围内"
            assert (
                content[c.start_at : c.end_at].strip().startswith(c.content[:10].strip()[:5])
                or c.content[:5] in content[c.start_at : c.end_at]
            )
        assert [c.chunk_index for c in chunks] == list(range(len(chunks))), "chunk_index 顺序"

    def test_max_len_respected_and_title_path(self):
        content = "# 标题甲\n\n" + "特采放行须经MRB评审并记录追溯。" * 60  # ~1500 字
        chunks = chunk_text(content)
        assert all(len(c.content) <= MAX_LEN + 30 for c in chunks), "超长段必须二次切分"
        assert all("标题甲" in c.title_path for c in chunks), "title_path 应滚动携带"

    def test_short_content_single_chunk(self):
        assert len(chunk_text("短文档只有一句话。")) == 1


# ============================================================
# Embedded 参考实现（规格 14 v1.2 主协议）
# ============================================================


class TestEmbeddedGateway:
    def test_ingest_idempotent_by_doc_id(self, gw):
        docs = [make_doc(i) for i in range(3)]
        r1 = gw.ingest_documents(PROJECT, docs)
        assert (r1.accepted, r1.deduped) == (3, 0)
        r2 = gw.ingest_documents(PROJECT, docs)  # 同 doc_id 重推 → 全去重
        assert (r2.accepted, r2.deduped) == (0, 3)

    def test_stats_invariant(self, gw):
        before = gw.stats(PROJECT)
        gw.ingest_documents(PROJECT, [make_doc(i) for i in range(10, 12)])
        s = gw.stats(PROJECT)
        assert s.documents == before.documents + 2
        assert s.parsing == 0, "同步实现 parsing 恒 0（规格 §1）"
        assert (s.parse_failed or 0) == 0
        assert s.chunks and s.chunks > 0

    def test_search_hit_traceability_five_fields(self, gw):
        gw.ingest_documents(PROJECT, [make_doc(20)])
        hits = gw.search(PROJECT, MARKER, top_k=5)
        assert hits, "标记必须命中"
        hit = hits[0]
        assert 0.0 <= hit.score <= 1.0
        assert hit.entry_type == "chunk"
        src = hit.source
        assert src.filename and src.knowledge_id
        assert src.chunk_index is not None and src.start_at is not None and src.end_at is not None

    def test_search_empty_result(self, gw):
        assert gw.search(PROJECT, f"NOMATCH{MARKER}", top_k=3) == []

    def test_search_blank_query_invalid_request(self, gw):
        with pytest.raises(KBContractError) as ei:
            gw.search(PROJECT, "  ")
        assert ei.value.code == "invalid_request"

    def test_curate_lifecycle(self, gw):
        entry = make_entry(1)
        entry_id, status = gw.curate(PROJECT, entry)
        assert status == "pending"
        total, entries = gw.list_pending(PROJECT)
        assert total == 1 and entries[0]["entry_id"] == entry_id
        # 幂等:同 origin+question_pattern → 既有 entry_id
        entry_id2, _ = gw.curate(PROJECT, entry)
        assert entry_id2 == entry_id
        # rejected 条目不可见
        e2_id, _ = gw.curate(PROJECT, make_entry(2))
        assert gw.reject_entry(PROJECT, e2_id, reason="t") == "rejected"
        assert not [
            h
            for h in gw.search(PROJECT, MARKER, top_k=10)
            if h.entry_type == "curated" and h.source.knowledge_id == e2_id
        ]
        # confirm(带终稿)→ 检索命中 curated
        assert gw.confirm_entry(PROJECT, entry_id, edited={"answer": entry.answer + "(终稿)"}) == "confirmed"
        curated = [h for h in gw.search(PROJECT, MARKER, top_k=10) if h.entry_type == "curated"]
        assert curated and curated[0].source.knowledge_id == entry_id
        # 幂等 confirm / rejected 不可再 confirm
        assert gw.confirm_entry(PROJECT, entry_id) == "confirmed"
        with pytest.raises(KBContractError) as ei:
            gw.confirm_entry(PROJECT, e2_id)
        assert ei.value.code == "not_found"

    def test_not_found(self, gw):
        with pytest.raises(KBContractError) as ei:
            gw.confirm_entry(PROJECT, "ke-nonexistent")
        assert (ei.value.http_status, ei.value.code) == (404, "not_found")

    def test_appendix_a_chunk_mode(self, gw):
        chunks = [
            {
                "id": f"{MARKER}:c{i}",
                "content": f"{MARKER} 降级块{i} 内容。",
                "source": {"filename": "probe.md", "para_idx": i, "doc_id": MARKER},
                "metadata": {"title_path": "附录A"},
            }
            for i in range(2)
        ]
        r1 = gw.ingest_chunks(PROJECT, chunks)
        assert (r1.accepted, r1.deduped) == (2, 0)
        r2 = gw.ingest_chunks(PROJECT, chunks)  # 幂等按 chunk.id
        assert (r2.accepted, r2.deduped) == (0, 2)

    def test_appendix_a_invalid_chunk(self, gw):
        with pytest.raises(KBContractError) as ei:
            gw.ingest_chunks(PROJECT, [{"content": "缺id"}])
        assert ei.value.code == "invalid_chunk"

    def test_get_document_roundtrip(self, gw):
        gw.ingest_documents(PROJECT, [make_doc(30)])
        doc = gw.get_document(PROJECT, f"doc-{MARKER}-30")
        assert doc["metadata"]["doc_id"] == f"doc-{MARKER}-30"


# ============================================================
# 工厂与降级
# ============================================================


class TestFactoryAndFallback:
    def test_factory_embedded_by_default(self, monkeypatch):
        import src.config as config

        monkeypatch.setattr(config, "get_settings", lambda: config.Settings(knowledge_db_path=":memory:"))
        from src.knowledge import gateway as gw_mod

        monkeypatch.setattr(gw_mod, "get_settings", lambda: config.Settings(knowledge_db_path=":memory:"))
        reset_knowledge_gateway()
        try:
            instance = gw_mod.get_knowledge_gateway()
            assert isinstance(instance, EmbeddedKnowledgeGateway)
        finally:
            reset_knowledge_gateway()

    def test_fallback_degrades_on_gateway_error(self):
        class BrokenRemote:
            def __init__(self):
                self.closed = False

            def search(self, *a, **kw):
                raise KnowledgeGatewayError("connection refused")

            def health(self):
                raise KnowledgeGatewayError("down")

            def close(self):
                self.closed = True

        embedded = EmbeddedKnowledgeGateway(":memory:")
        fb = FallbackKnowledgeGateway(BrokenRemote(), embedded)
        try:
            hits = fb.search("p", "任意查询")  # Remote 挂 → 降级 Embedded 正常返回
            assert hits == []
            assert fb.degraded_since is not None, "必须留下降级标记"
        finally:
            embedded.close()


# ============================================================
# KbOsGateway(Envelope 解包 / 错误映射)
# ============================================================


class TestKbOsGateway:
    @staticmethod
    def _client(handler) -> KbOsGateway:
        gw = KbOsGateway("http://kb-os.test", token="kbos-x")
        gw._http = httpx.Client(
            base_url="http://kb-os.test",
            headers={"Authorization": "Bearer kbos-x"},
            transport=httpx.MockTransport(handler),
            trust_env=False,
        )
        return gw

    def test_search_envelope_unwrap(self):
        def handler(request):
            assert request.url.path == "/api/v1/knowledge/search"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "message": "success",
                    "request_id": "req-1",
                    "data": {
                        "items": [
                            {
                                "snippet": "让步放行需取得客户书面特采许可",
                                "score": 0.87,
                                "metadata": {
                                    "filename": "质检手册.md",
                                    "chunk_index": 34,
                                    "start_at": 8210,
                                    "end_at": 8790,
                                    "knowledge_id": "k-1",
                                    "chunk_type": "text",
                                },
                            }
                        ]
                    },
                },
            )

        gw = self._client(handler)
        try:
            hits = gw.search("p", "特采放行")
            assert hits[0].source.filename == "质检手册.md"
            assert hits[0].source.knowledge_id == "k-1"
            assert hits[0].entry_type == "chunk"
        finally:
            gw.close()

    def test_error_key_preferred_and_contract_error(self):
        def handler(request):
            return httpx.Response(403, json={"code": 40301, "message": "越权", "error_key": "scope_denied"})

        gw = self._client(handler)
        try:
            with pytest.raises(KBContractError) as ei:
                gw.search("p", "q")
            assert ei.value.code == "scope_denied"  # error_key 优先
        finally:
            gw.close()

    def test_numeric_fallback_and_degraded(self):
        def handler(request):
            return httpx.Response(200, json={"code": 50002, "message": "下游不可用"})

        gw = self._client(handler)
        try:
            with pytest.raises(KnowledgeGatewayError) as ei:
                gw.search("p", "q")
            assert ei.value.degraded, "50002 → 触发降级"
        finally:
            gw.close()

    def test_stats_entries_mapping(self):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "documents": 5,
                        "chunks": 40,
                        "parsing": 2,
                        "parse_failed": 1,
                        "entries": {"pending": 3, "confirmed": 7, "rejected": 1},
                    },
                },
            )

        gw = self._client(handler)
        try:
            s = gw.stats("p")
            assert (s.documents, s.parsing, s.parse_failed) == (5, 2, 1)
            assert (s.curated, s.pending, s.rejected) == (7, 3, 1)
        finally:
            gw.close()


# ============================================================
# spec14 参考服务(HTTP 契约面)
# ============================================================


class TestSpec14Service:
    @staticmethod
    def _client(token: str = "") -> TestClient:
        app = create_app(gateway=EmbeddedKnowledgeGateway(":memory:"), token=token)
        return TestClient(app)

    def test_p0_loop(self):
        with self._client() as c:
            assert c.get("/health").json()["status"] == "ok"
            docs = {
                "documents": [
                    {
                        "title": f"probe-{MARKER}-{i}.md",
                        "content": f"{MARKER} 第{i}条:让步放行需取得客户书面特采许可,经MRB评审。{MARKER}",
                        "metadata": {"doc_id": f"doc-{MARKER}-{i}"},
                    }
                    for i in range(3)
                ]
            }
            r = c.post("/ingest", json=docs)
            assert r.status_code == 200 and r.json() == {"accepted": 3, "deduped": 0}
            assert c.post("/ingest", json=docs).json() == {"accepted": 0, "deduped": 3}
            stats = c.get("/stats").json()
            assert (stats["documents"], stats["parsing"]) == (3, 0)
            hits = c.post("/search", json={"query": MARKER, "top_k": 5}).json()["hits"]
            assert hits and hits[0]["source"]["filename"]
            assert c.post("/search", json={"query": f"NOMATCH{MARKER}"}).json() == {"hits": []}

    def test_error_branches(self):
        with self._client() as c:
            r = c.post("/search", json={"top_k": 5})  # 缺 query
            assert (r.status_code, r.json()["error"]["code"]) == (400, "invalid_request")
            r = c.post(
                "/ingest",
                json={
                    "documents": [
                        {"title": "t", "content": "c", "metadata": {"doc_id": f"{MARKER}-ovr-{i}"}} for i in range(51)
                    ]
                },
            )
            assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")
            r = c.post("/entries/ke-none/confirm")
            assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")

    def test_p1_loop(self):
        with self._client() as c:
            r = c.post("/curate", json={"entry": make_entry(9).to_payload()})
            assert r.json()["status"] == "pending"
            entry_id = r.json()["entry_id"]
            pending = c.get("/pending").json()
            assert pending["total"] >= 1
            assert any(e["entry_id"] == entry_id for e in pending["entries"])
            r = c.post(f"/entries/{entry_id}/confirm", json={"answer": "FDE 修订终稿"})
            assert r.json()["status"] == "confirmed"
            assert c.post(f"/entries/{entry_id}/confirm").json()["status"] == "confirmed"
            hits = c.post("/search", json={"query": MARKER, "top_k": 10}).json()["hits"]
            assert any(h["entry_type"] == "curated" for h in hits)

    def test_auth_401(self):
        with self._client(token="secret-key") as c:
            r = c.get("/stats")  # TestClient 默认无 Authorization 头
            assert (r.status_code, r.json()["error"]["code"]) == (401, "unauthorized")
            c.headers["Authorization"] = "Bearer secret-key"
            assert c.get("/stats").status_code == 200

    def test_document_roundtrip(self):
        with self._client() as c:
            c.post(
                "/ingest",
                json={"documents": [{"title": "probe.md", "content": f"{MARKER} 原文", "metadata": {"doc_id": "d-1"}}]},
            )
            doc = c.get("/documents/d-1")
            assert doc.status_code == 200 and doc.json()["content"] == f"{MARKER} 原文"
