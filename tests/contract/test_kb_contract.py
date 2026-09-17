"""知识库契约场景测试(实现无关)——W3 对拍用例集。

同一组场景,两种断言适配(KB_PROFILE=spec14|kbos)分别对任意实现运行:
  - P0(联调最小集):上传→建库→检索闭环 + stats 口径 + 错误分支
  - P1(交互闭环):curate→pending→confirm/reject + 幂等 + 404

断言依据:docs/14-知识库接口规格.md v1.2(§1 总则/§3 端点/§4 错误码表)。
运行方式见 tests/contract/README.md。
"""

from __future__ import annotations

import os
import uuid

import pytest

from .conftest import KB_TOKEN
from .core import KBError, make_doc, make_entry

# 集成性质:需 KB_BASE_URL 指向运行中的知识库服务(参考服务:uvicorn src.knowledge.server:app)
if not os.environ.get("KB_BASE_URL"):
    pytest.skip(
        "契约测试需指定 KB_BASE_URL(集成用例,默认套件跳过;用法见 tests/contract/README.md)", allow_module_level=True
    )

# ============================================================
# P0:上传 → 建库 → 检索 闭环(联调最小集)
# ============================================================


@pytest.mark.p0
def test_health(kb):
    """GET /health:status ∈ {ok, degraded}(degraded 合法——观测得到即可)"""
    data = kb.health()
    assert data.get("status") in ("ok", "degraded"), data


@pytest.mark.p0
def test_ingest_documents_and_idempotent(kb, marker):
    """文档级推送:accepted/deduped 计数;幂等按 metadata.doc_id(重复推送全部去重)"""
    docs = [make_doc(marker, i) for i in range(3)]
    assert kb.ingest_documents(docs) == (3, 0)
    assert kb.ingest_documents(docs) == (0, 3)  # 幂等:同 doc_id 重推 → deduped


@pytest.mark.p0
def test_stats_invariant_and_ready(kb, wait, marker):
    """stats 口径 + 三元不变量核账:documents+parsing(+parse_failed)=累计接受;
    就绪判据 parsing == 0(规格 §3.6)"""
    before = wait(kb)  # 快照前先收敛在途索引(异步实现必需;同步实现首次轮询即过,零开销)
    kb.ingest_documents([make_doc(marker, 10 + i) for i in range(2)])
    after = wait(kb, expect_documents=before.documents + 2)
    assert after.documents == before.documents + 2
    assert after.parsing == 0
    assert after.parse_failed in (None, 0), "测试环境下不应有解析失败"


@pytest.mark.p0
def test_search_hit_with_traceability(kb, wait, marker):
    """就绪后按唯一标记命中;溯源五字段必填(filename/chunk_index/start_at/end_at/knowledge_id)"""
    expect = kb.stats().documents + 1
    kb.ingest_documents([make_doc(marker, 20)])
    wait(kb, expect_documents=expect)
    hits = kb.search(marker, top_k=5)
    assert hits, "parsing==0 后必须能按唯一标记命中"
    hit = hits[0]
    assert 0.0 <= hit.score <= 1.0
    assert hit.entry_type in ("chunk", "curated")
    src = hit.source
    assert src.filename, "溯源必填:filename"
    assert src.knowledge_id, "溯源必填:knowledge_id"
    assert src.chunk_index is not None, "溯源必填:chunk_index"
    assert src.start_at is not None and src.end_at is not None, "溯源必填:字符偏移"


@pytest.mark.p0
def test_search_empty_result(kb, marker):
    """空结果返回 [] 不报错(规格 §3.2)"""
    assert kb.search(f"NOMATCH{marker}查无此物", top_k=3) == []


@pytest.mark.p0
def test_error_invalid_request(kb):
    """缺必填字段 → 400 invalid_request(规格 §4)"""
    with pytest.raises(KBError) as ei:
        kb.trigger_invalid_request()
    assert ei.value.http_status == 400
    assert ei.value.code == "invalid_request"


@pytest.mark.p0
def test_error_over_limit_batch(kb):
    """单批 >50 篇 → 按适配预期拒绝(spec14: payload_too_large / kbos: invalid_request)"""
    with pytest.raises(KBError) as ei:
        kb.trigger_over_limit()
    assert ei.value.http_status in (400, 413)
    assert ei.value.code in kb.expectations.over_limit


# ============================================================
# P1:审核交互闭环(curate → pending → confirm/reject)
# ============================================================


@pytest.mark.p1
def test_curate_pending_and_idempotent(kb, marker):
    """提交即 pending(不进检索池);幂等:同 origin+question_pattern 返回既有 entry_id"""
    entry = make_entry(marker, 1)
    entry_id, status = kb.curate(entry)
    assert status == "pending"
    total, entries = kb.list_pending(page=1, page_size=50)
    assert total >= 1
    assert any(e.get("entry_id") == entry_id for e in entries), "pending 队列必须可见"
    entry_id2, status2 = kb.curate(entry)
    assert (entry_id2, status2) == (entry_id, "pending"), "curate 幂等口径"


@pytest.mark.p1
def test_confirm_flow_and_search_curated(kb, wait, marker):
    """confirm(可带人工终稿)→ 进检索池,entry_type=curated;最终一致口径统一走 wait"""
    entry = make_entry(marker, 2)
    entry_id, _ = kb.curate(entry)
    assert (
        kb.confirm(
            entry_id,
            edited={
                "question_pattern": entry.question_pattern,
                "answer": entry.answer + "(FDE 终稿)",
            },
        )
        == "confirmed"
    )
    wait(kb, expect_documents=kb.stats().documents)
    curated = [h for h in kb.search(marker, top_k=10) if h.entry_type == "curated"]
    assert curated, "confirm 后必须可检索命中 curated 条目"


@pytest.mark.p1
def test_reject_flow_invisible(kb, marker):
    """reject → 保留记录可审计但不得进入检索池"""
    entry = make_entry(marker, 3)
    entry_id, _ = kb.curate(entry)
    assert kb.reject(entry_id, reason="contract-test-reject") == "rejected"
    hits = kb.search(entry.question_pattern, top_k=5)
    assert not [h for h in hits if h.entry_type == "curated" and h.source.knowledge_id == entry_id], (
        "rejected 条目不得出现在检索结果"
    )


@pytest.mark.p1
def test_confirm_idempotent(kb, marker):
    """重复 confirm → 返回当前终态(终态不可逆,规格 §3.5)"""
    entry_id, _ = kb.curate(make_entry(marker, 4))
    assert kb.confirm(entry_id) == "confirmed"
    assert kb.confirm(entry_id) == "confirmed"


@pytest.mark.p1
def test_entry_not_found(kb):
    """不存在的条目 → 404 not_found(v1.2 泛化码)"""
    with pytest.raises(KBError) as ei:
        kb.confirm(f"ke-nonexistent-{uuid.uuid4().hex[:8]}")
    assert ei.value.http_status == 404
    assert ei.value.code == "not_found"


# ============================================================
# 鉴权负例(配置 KB_TOKEN 时启用)
# ============================================================


@pytest.mark.p0
@pytest.mark.skipif(not KB_TOKEN, reason="未配置 KB_TOKEN 时跳过(scoped key 未启用场景)")
def test_unauthorized_without_token(kb):
    """无凭证访问只读端点 → 401 unauthorized(规格 §4)"""
    status, code = kb.probe_no_auth()
    assert status == 401, f"期望 401,实际 {status}"
    assert code == "unauthorized", f"期望错误码 unauthorized,实际 {code}"
