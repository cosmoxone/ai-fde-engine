"""EmbeddedKnowledgeGateway——契约参考实现（SQLite FTS5 trigram，零依赖兜底）。

「参考实现即规格」：本类实现规格 14 v1.2 全部主协议语义，第三方实现以其为行为基准：
- 文档级 ingest（幂等按 metadata.doc_id，缺省 title+内容哈希）→ 内嵌切块器 → FTS5 直写
- 同步索引：parsing 恒 0（规格 §1：同步实现同样合规）
- 检索：FTS5 trigram MATCH（中文友好），BM25 归一化 0-1；curated 推荐加权（规格 §3.2）
- curate→pending→confirm/reject 生命周期（幂等 + 终态不可逆，规格 §3.3/§3.5）
- 附录 A chunk 降级模式（ingest_chunks，幂等按 chunk.id）

数据落点：独立 SQLite 文件（默认 {data_dir}/knowledge.db；独立连接避免与 storage 层
锁竞争，后续如需并入 aifde.db 再迁移）。进程内多项目按 project_id 隔离（规格 §1：
Embedded 模式项目上下文由 Gateway 抽象内部管理）。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid

from .chunker import chunk_text
from .types import DocSpec, EntrySpec, Hit, IngestReport, KBContractError, Source, Stats

_TOKENIZERS = ("trigram", "unicode61")  # trigram 需 SQLite>=3.34，失败降级 unicode61

_SCHEMA_DOC = """
CREATE TABLE IF NOT EXISTS kb_documents(
  project_id TEXT NOT NULL, doc_id TEXT NOT NULL, title TEXT, content TEXT,
  metadata_json TEXT, status TEXT DEFAULT 'ready', created_at REAL,
  PRIMARY KEY(project_id, doc_id))
"""
_SCHEMA_ENTRIES = """
CREATE TABLE IF NOT EXISTS kb_entries(
  project_id TEXT NOT NULL, entry_id TEXT NOT NULL, question_pattern TEXT, answer TEXT,
  origin TEXT, suggested_by TEXT, similar_json TEXT, status TEXT, created_at REAL,
  PRIMARY KEY(project_id, entry_id),
  UNIQUE(project_id, origin, question_pattern))
"""
_SCHEMA_CHUNK_KEYS = """
CREATE TABLE IF NOT EXISTS kb_chunk_keys(
  project_id TEXT NOT NULL, chunk_uid TEXT NOT NULL, PRIMARY KEY(project_id, chunk_uid))
"""


class EmbeddedKnowledgeGateway:
    """契约的进程内参考实现（模式 B，默认；规格 14 v1.2）"""

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join("data", "knowledge.db")
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA_DOC)
        self._conn.execute(_SCHEMA_ENTRIES)
        self._conn.execute(_SCHEMA_CHUNK_KEYS)
        self._fts_table = self._create_fts()
        self._conn.commit()

    # ---------- 内部 ----------

    def _create_fts(self) -> str:
        last_error: Exception | None = None
        for tokenizer in _TOKENIZERS:
            name = f"kb_chunks_{tokenizer}"
            ddl = (
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING fts5("
                "content, project_id UNINDEXED, doc_id UNINDEXED, filename UNINDEXED, "
                "chunk_index UNINDEXED, start_at UNINDEXED, end_at UNINDEXED, "
                f"title_path UNINDEXED, tokenize='{tokenizer}')"
            )
            try:
                self._conn.execute(ddl)
                return name
            except sqlite3.OperationalError as exc:  # trigram 不可用等
                last_error = exc
        raise RuntimeError(f"FTS5 虚表创建失败: {last_error}")

    def _doc_uid(self, doc: DocSpec) -> str:
        if doc.metadata.get("doc_id"):
            return str(doc.metadata["doc_id"])
        digest = hashlib.sha1(f"{doc.title}|{doc.content}".encode("utf-8")).hexdigest()
        return f"hashed-{digest[:16]}"

    @staticmethod
    def _fts_row_to_hit(row: sqlite3.Row, score: float) -> Hit:
        return Hit(
            content=row["content"],
            source=Source(
                filename=row["filename"],
                chunk_index=row["chunk_index"],
                start_at=row["start_at"],
                end_at=row["end_at"],
                knowledge_id=row["doc_id"],
            ),
            score=score,
            entry_type="chunk",
        )

    # ---------- 观测面 ----------

    def health(self) -> dict:
        return {"status": "ok", "version": "embedded-0.4.0", "parsing": 0}

    def stats(self, project_id: str) -> Stats:
        cur = self._conn.execute(
            "SELECT status, COUNT(*) n FROM kb_documents WHERE project_id=? GROUP BY status", (project_id,)
        )
        by_status = {row["status"]: row["n"] for row in cur}
        cur = self._conn.execute(
            "SELECT status, COUNT(*) n FROM kb_entries WHERE project_id=? GROUP BY status", (project_id,)
        )
        entries = {row["status"]: row["n"] for row in cur}
        chunks = self._conn.execute(
            f"SELECT COUNT(*) n FROM {self._fts_table} WHERE project_id=?", (project_id,)
        ).fetchone()["n"]
        return Stats(
            documents=by_status.get("ready", 0),
            parsing=0,  # 同步直写，恒 0（规格 §1）
            curated=entries.get("confirmed", 0),
            pending=entries.get("pending", 0),
            chunks=chunks,
            parse_failed=by_status.get("failed", 0),
            rejected=entries.get("rejected", 0),
        )

    # ---------- P0：文档级 ingest / search ----------

    def ingest_documents(self, project_id: str, docs: list[DocSpec]) -> IngestReport:
        accepted = deduped = 0
        for doc in docs:
            doc_id = self._doc_uid(doc)
            try:
                self._conn.execute(
                    "INSERT INTO kb_documents(project_id, doc_id, title, content, metadata_json,"
                    " status, created_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        project_id,
                        doc_id,
                        doc.title,
                        doc.content,
                        json.dumps(doc.metadata, ensure_ascii=False),
                        "ready",
                        time.time(),
                    ),
                )
            except sqlite3.IntegrityError:  # 幂等：同 doc_id 重推 → deduped
                deduped += 1
                continue
            accepted += 1
            for chunk in chunk_text(doc.content):
                self._conn.execute(
                    f"INSERT INTO {self._fts_table}"
                    "(content, project_id, doc_id, filename, chunk_index, start_at, end_at, title_path)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (
                        chunk.content,
                        project_id,
                        doc_id,
                        doc.title,
                        chunk.chunk_index,
                        chunk.start_at,
                        chunk.end_at,
                        chunk.title_path,
                    ),
                )
        self._conn.commit()
        return IngestReport(accepted=accepted, deduped=deduped)

    def ingest_chunks(self, project_id: str, chunks: list[dict]) -> IngestReport:
        """附录 A 降级模式：chunk 级推送（幂等按 chunk.id；溯源坐标 caller 侧可信度降低）"""
        accepted = deduped = 0
        for chunk in chunks:
            if not chunk.get("id") or not chunk.get("content"):
                raise KBContractError("invalid_chunk", "chunk 缺 id/content（规格附录A）", 400)
            try:
                self._conn.execute(
                    "INSERT INTO kb_chunk_keys(project_id, chunk_uid) VALUES(?,?)", (project_id, str(chunk["id"]))
                )
            except sqlite3.IntegrityError:
                deduped += 1
                continue
            accepted += 1
            source = chunk.get("source") or {}
            metadata = chunk.get("metadata") or {}
            self._conn.execute(
                f"INSERT INTO {self._fts_table}"
                "(content, project_id, doc_id, filename, chunk_index, start_at, end_at, title_path)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    str(chunk["content"]),
                    project_id,
                    str(source.get("doc_id") or chunk["id"]),
                    source.get("filename") or "",
                    source.get("para_idx") or 0,
                    source.get("start_at") or 0,
                    source.get("end_at") or 0,
                    metadata.get("title_path") or "",
                ),
            )
        self._conn.commit()
        return IngestReport(accepted=accepted, deduped=deduped)

    def search(self, project_id: str, query: str, top_k: int = 5, entry_type: str = "any") -> list[Hit]:
        if not query or not query.strip():
            raise KBContractError("invalid_request", "query 不能为空（规格 §3.2）", 400)
        hits: list[Hit] = []
        if entry_type in ("any", "chunk"):
            hits.extend(self._search_chunks(project_id, query.strip(), top_k))
        if entry_type in ("any", "curated"):
            hits.extend(self._search_curated(project_id, query.strip(), top_k))
        # 排序：分数降序；curated 推荐加权（规格 §3.2：加权而非固定置顶）
        for hit in hits:
            if hit.entry_type == "curated":
                hit.score = min(1.0, hit.score * 1.05)
        hits.sort(key=lambda h: (-h.score, 0 if h.entry_type == "curated" else 1))
        return hits[:top_k]

    @staticmethod
    def _match_tokens(query: str, limit: int = 4) -> list[str]:
        """查询分片（v0.4-c 检索质量）：按标点/空白切分，长片段优先——自然语言长句
        整串 phrase 几乎必不命中（trigram 连续匹配语义），分片 OR 是必要降级。"""
        import re

        parts = re.split(r'[\s\uff0c\u3002\uff1b\u3001,.;:!?\uff01\uff1f\uff08\uff09()\[\]{}"\']+', query)
        tokens = {s.strip() for s in parts if len(s.strip()) >= 2}
        return sorted(tokens, key=len, reverse=True)[:limit]

    def _search_chunks(self, project_id: str, query: str, top_k: int) -> list[Hit]:
        sql_match = (
            f"SELECT content, project_id, doc_id, filename, chunk_index, start_at, end_at,"
            f" title_path, bm25({self._fts_table}) AS rank FROM {self._fts_table}"
            " WHERE project_id=? AND {t} MATCH ? ORDER BY rank LIMIT ?"
        ).replace("{t}", self._fts_table)
        # 三级降级：整串 phrase → 分片 OR（自然语言长句）→ LIKE 兜底（最短可匹配片段）
        rows = self._conn.execute(sql_match, (project_id, f'"{query}"', top_k)).fetchall()
        if not rows:
            tokens = self._match_tokens(query)
            if tokens:
                expr = " OR ".join(f'"{tok}"' for tok in tokens)
                rows = self._conn.execute(sql_match, (project_id, expr, top_k)).fetchall()
        if not rows:
            tokens = self._match_tokens(query, limit=1)
            like = f"%{tokens[0]}%" if tokens else f"%{query}%"
            rows = self._conn.execute(
                f"SELECT content, project_id, doc_id, filename, chunk_index, start_at, end_at,"
                f" title_path, 0.0 AS rank FROM {self._fts_table}"
                " WHERE project_id=? AND content LIKE ? LIMIT ?",
                (project_id, like, top_k),
            ).fetchall()
        result = []
        for row in rows:
            raw_rank = row["rank"]
            score = 1.0 / (1.0 + abs(raw_rank)) if raw_rank else 0.5  # BM25 归一化 0-1
            result.append(self._fts_row_to_hit(row, score))
        return result

    def _search_curated(self, project_id: str, query: str, top_k: int) -> list[Hit]:
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT entry_id, question_pattern, answer FROM kb_entries"
            " WHERE project_id=? AND status='confirmed' AND"
            " (question_pattern LIKE ? OR answer LIKE ? OR similar_json LIKE ?) LIMIT ?",
            (project_id, like, like, like, top_k),
        ).fetchall()
        return [
            Hit(
                content=f"{row['question_pattern']}\n{row['answer']}",
                source=Source(
                    filename=f"curated:{row['entry_id']}",
                    chunk_index=0,
                    start_at=0,
                    end_at=len(row["answer"]),
                    knowledge_id=row["entry_id"],
                ),
                score=0.9,  # 精确 LIKE 命中给高分；最终经推荐加权与排序合并
                entry_type="curated",
            )
            for row in rows
        ]

    # ---------- P1：条目生命周期 ----------

    def curate(self, project_id: str, entry: EntrySpec) -> tuple[str, str]:
        similar = json.dumps(entry.similar_questions or [], ensure_ascii=False)
        try:
            entry_id = f"ke-{uuid.uuid4().hex[:12]}"
            self._conn.execute(
                "INSERT INTO kb_entries(project_id, entry_id, question_pattern, answer, origin,"
                " suggested_by, similar_json, status, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    entry_id,
                    entry.question_pattern,
                    entry.answer,
                    entry.origin,
                    entry.suggested_by,
                    similar,
                    "pending",
                    time.time(),
                ),
            )
        except sqlite3.IntegrityError:  # 幂等：同 origin+question_pattern 返回既有 entry_id
            row = self._conn.execute(
                "SELECT entry_id, status FROM kb_entries WHERE project_id=? AND origin IS ? AND question_pattern=?",
                (project_id, entry.origin, entry.question_pattern),
            ).fetchone()
            if row:
                return row["entry_id"], row["status"]
            raise
        self._conn.commit()
        return entry_id, "pending"

    def list_pending(self, project_id: str, page: int = 1, page_size: int = 50) -> tuple[int, list[dict]]:
        total = self._conn.execute(
            "SELECT COUNT(*) n FROM kb_entries WHERE project_id=? AND status='pending'", (project_id,)
        ).fetchone()["n"]
        rows = self._conn.execute(
            "SELECT entry_id, question_pattern, answer, origin, suggested_by, created_at"
            " FROM kb_entries WHERE project_id=? AND status='pending'"
            " ORDER BY created_at LIMIT ? OFFSET ?",
            (project_id, page_size, (max(page, 1) - 1) * page_size),
        ).fetchall()
        entries = [
            {
                "entry_id": r["entry_id"],
                "draft": {
                    "question_pattern": r["question_pattern"],
                    "answer": r["answer"],
                    "origin": r["origin"],
                    "suggested_by": r["suggested_by"],
                },
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return total, entries

    def _get_entry(self, project_id: str, entry_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM kb_entries WHERE project_id=? AND entry_id=?", (project_id, entry_id)
        ).fetchone()
        if not row:
            raise KBContractError("not_found", f"条目不存在: {entry_id}（规格 §3.5）", 404)
        return row

    def confirm_entry(self, project_id: str, entry_id: str, edited: dict | None = None) -> str:
        row = self._get_entry(project_id, entry_id)
        if row["status"] == "rejected":  # 终态不可逆（规格 §3.5）
            raise KBContractError("not_found", f"条目已 rejected，不可 confirm: {entry_id}", 404)
        if row["status"] == "confirmed":  # 幂等：返回当前终态
            return "confirmed"
        question = (edited or {}).get("question_pattern") or row["question_pattern"]
        answer = (edited or {}).get("answer") or row["answer"]
        self._conn.execute(
            "UPDATE kb_entries SET status='confirmed', question_pattern=?, answer=? WHERE project_id=? AND entry_id=?",
            (question, answer, project_id, entry_id),
        )
        self._conn.commit()
        return "confirmed"

    def reject_entry(self, project_id: str, entry_id: str, reason: str | None = None) -> str:
        row = self._get_entry(project_id, entry_id)
        if row["status"] == "confirmed":  # 幂等：返回当前终态（已 confirmed 不可逆）
            return "confirmed"
        if row["status"] == "rejected":
            return "rejected"
        self._conn.execute(
            "UPDATE kb_entries SET status='rejected' WHERE project_id=? AND entry_id=?", (project_id, entry_id)
        )
        self._conn.commit()
        return "rejected"

    # ---------- 溯源回查 ----------

    def get_document(self, project_id: str, knowledge_id: str) -> dict:
        row = self._conn.execute(
            "SELECT doc_id, title, content, metadata_json, created_at FROM kb_documents"
            " WHERE project_id=? AND doc_id=?",
            (project_id, knowledge_id),
        ).fetchone()
        if not row:
            raise KBContractError("not_found", f"文档不存在: {knowledge_id}", 404)
        return {
            "knowledge_id": row["doc_id"],
            "title": row["title"],
            "content": row["content"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "created_at": row["created_at"],
        }

    def close(self) -> None:
        self._conn.close()
