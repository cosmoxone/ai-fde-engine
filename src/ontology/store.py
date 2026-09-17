"""EmbeddedOntologyStore——本体存储参考实现（SQLite）。

"参考实现即规格"（对齐知识库 Embedded 的原则，契约 20 号 §6）：
- 增量 merge 幂等：同 (project, type, name) 实体属性合并、source_docs 追加去重——
  重复抽取/重推文档图规模不增长（13 号 §五 验收"增量不重复计数"）；
- 人工删除为软删且**不被后续 upsert 复活**（13 号 §五 风险表：Dashboard 人工删除接口）；
- 孤儿关系（端点实体不存在或已删除）不入库，计入 skipped_orphan_relations；
- 已抽取文档按 doc_ref 记账，service 层据此跳过（force 可重抽，merge 幂等保数量不变）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .types import Entity, MergeReport, OntologyGraph, Relation, Rule

_SCHEMA = """
CREATE TABLE IF NOT EXISTS onto_entities (
    project_id  TEXT NOT NULL,
    id          TEXT NOT NULL,
    type        TEXT NOT NULL,
    name        TEXT NOT NULL,
    properties  TEXT NOT NULL DEFAULT '{}',
    confidence  REAL NOT NULL DEFAULT 0.8,
    source_docs TEXT NOT NULL DEFAULT '[]',
    status      TEXT NOT NULL DEFAULT 'active',
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    PRIMARY KEY (project_id, id)
);
CREATE INDEX IF NOT EXISTS idx_onto_entities_name ON onto_entities(project_id, name);
CREATE TABLE IF NOT EXISTS onto_relations (
    project_id    TEXT NOT NULL,
    from_entity   TEXT NOT NULL,
    to_entity     TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    source_docs   TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (project_id, from_entity, to_entity, relation_type)
);
CREATE TABLE IF NOT EXISTS onto_rules (
    project_id  TEXT NOT NULL,
    id          TEXT NOT NULL,
    condition   TEXT NOT NULL,
    conclusion  TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.8,
    source_docs TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (project_id, id)
);
CREATE TABLE IF NOT EXISTS onto_extracted_docs (
    project_id   TEXT NOT NULL,
    doc_ref      TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    PRIMARY KEY (project_id, doc_ref)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EmbeddedOntologyStore:
    """单文件 SQLite；线程安全（进程内单例由 gateway 工厂管理）。"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # ---------------------------------------------------------------- merge
    def upsert_batch(
        self,
        project_id: str,
        entities: list[Entity],
        relations: list[Relation],
        rules: list[Rule],
        doc_ref: str = "",
    ) -> MergeReport:
        report = MergeReport(doc_ref=doc_ref)
        now = _now()
        with self._lock, self._conn() as conn:
            existing = {
                row["id"]: row for row in conn.execute("SELECT * FROM onto_entities WHERE project_id=?", (project_id,))
            }
            known: dict[str, bool] = {}  # 本次批内实体也参与端点校验

            for ent in entities:
                ent.name = (ent.name or "").strip()
                ent.type = (ent.type or "").strip()
                if not ent.name or not ent.type:
                    continue
                if not ent.id:
                    ent.id = Entity.make_id(ent.type, ent.name)
                row = existing.get(ent.id)
                if row is not None and row["status"] == "deleted":
                    report.skipped_deleted_entities += 1  # 人工删除权威，不复活
                    continue
                src = list(dict.fromkeys([doc_ref, *ent.source_docs] if doc_ref else ent.source_docs))
                if row is None:
                    conn.execute(
                        "INSERT INTO onto_entities VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            project_id,
                            ent.id,
                            ent.type,
                            ent.name,
                            json.dumps(ent.properties, ensure_ascii=False),
                            float(ent.confidence),
                            json.dumps(src, ensure_ascii=False),
                            "active",
                            now,
                            now,
                        ),
                    )
                    report.entities_added += 1
                else:
                    merged_props = {**json.loads(row["properties"]), **ent.properties}
                    merged_src = json.loads(row["source_docs"]) + [s for s in src if s]
                    conn.execute(
                        "UPDATE onto_entities SET properties=?, confidence=?, source_docs=?, last_seen=? "
                        "WHERE project_id=? AND id=?",
                        (
                            json.dumps(merged_props, ensure_ascii=False),
                            max(float(row["confidence"]), float(ent.confidence)),
                            json.dumps(list(dict.fromkeys(merged_src)), ensure_ascii=False),
                            now,
                            project_id,
                            ent.id,
                        ),
                    )
                    report.entities_merged += 1
                existing[ent.id] = {"status": "active"}
                known[ent.id] = True

            for rel in relations:
                rt = (rel.relation_type or "").strip()
                if not rt:
                    continue
                if rel.from_entity not in known or rel.to_entity not in known:
                    report.skipped_orphan_relations += 1
                    continue
                row = conn.execute(
                    "SELECT source_docs FROM onto_relations WHERE project_id=? AND from_entity=? "
                    "AND to_entity=? AND relation_type=?",
                    (project_id, rel.from_entity, rel.to_entity, rt),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO onto_relations VALUES (?,?,?,?,?)",
                        (
                            project_id,
                            rel.from_entity,
                            rel.to_entity,
                            rt,
                            json.dumps([doc_ref] if doc_ref else [], ensure_ascii=False),
                        ),
                    )
                    report.relations_added += 1
                elif doc_ref:
                    merged = json.loads(row["source_docs"]) + [doc_ref]
                    conn.execute(
                        "UPDATE onto_relations SET source_docs=? WHERE project_id=? AND from_entity=? "
                        "AND to_entity=? AND relation_type=?",
                        (
                            json.dumps(list(dict.fromkeys(merged)), ensure_ascii=False),
                            project_id,
                            rel.from_entity,
                            rel.to_entity,
                            rt,
                        ),
                    )

            for rule in rules:
                if not (rule.condition or "").strip() or not (rule.conclusion or "").strip():
                    continue
                if not rule.id:
                    rule.id = Rule.make_id(rule.condition, rule.conclusion)
                row = conn.execute(
                    "SELECT source_docs FROM onto_rules WHERE project_id=? AND id=?",
                    (project_id, rule.id),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO onto_rules VALUES (?,?,?,?,?,?)",
                        (
                            project_id,
                            rule.id,
                            rule.condition.strip(),
                            rule.conclusion.strip(),
                            float(rule.confidence),
                            json.dumps([doc_ref] if doc_ref else [], ensure_ascii=False),
                        ),
                    )
                    report.rules_added += 1
                elif doc_ref:
                    merged = json.loads(row["source_docs"]) + [doc_ref]
                    conn.execute(
                        "UPDATE onto_rules SET source_docs=? WHERE project_id=? AND id=?",
                        (json.dumps(list(dict.fromkeys(merged)), ensure_ascii=False), project_id, rule.id),
                    )

            if doc_ref:
                conn.execute(
                    "INSERT OR REPLACE INTO onto_extracted_docs VALUES (?,?,?)",
                    (project_id, doc_ref, now),
                )
        return report

    # ---------------------------------------------------------------- 查询
    def _entity_rows(self, project_id: str, include_deleted: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM onto_entities WHERE project_id=?"
        if not include_deleted:
            sql += " AND status='active'"
        with self._conn() as conn:
            return list(conn.execute(sql, (project_id,)))

    def get_graph(self, project_id: str) -> OntologyGraph:
        ents = [
            Entity(
                id=r["id"],
                type=r["type"],
                name=r["name"],
                properties=json.loads(r["properties"]),
                confidence=r["confidence"],
                source_docs=json.loads(r["source_docs"]),
                first_seen=r["first_seen"],
                last_seen=r["last_seen"],
            )
            for r in self._entity_rows(project_id)
        ]
        active_ids = {e.id for e in ents}
        with self._conn() as conn:
            rels = [
                Relation(r["from_entity"], r["to_entity"], r["relation_type"], json.loads(r["source_docs"]))
                for r in conn.execute("SELECT * FROM onto_relations WHERE project_id=?", (project_id,))
                if r["from_entity"] in active_ids and r["to_entity"] in active_ids
            ]
            rules = [
                Rule(r["id"], r["condition"], r["conclusion"], r["confidence"], json.loads(r["source_docs"]))
                for r in conn.execute("SELECT * FROM onto_rules WHERE project_id=?", (project_id,))
            ]
        return OntologyGraph(project_id, ents, rels, rules)

    def find_entities(self, project_id: str, keyword: str, limit: int = 50) -> list[Entity]:
        kw = (keyword or "").strip().lower()
        out = []
        for r in self._entity_rows(project_id):
            if not kw or kw in r["name"].lower() or kw in r["type"].lower():
                out.append(
                    Entity(
                        id=r["id"],
                        type=r["type"],
                        name=r["name"],
                        properties=json.loads(r["properties"]),
                        confidence=r["confidence"],
                        source_docs=json.loads(r["source_docs"]),
                        first_seen=r["first_seen"],
                        last_seen=r["last_seen"],
                    )
                )
            if len(out) >= limit:
                break
        return out

    def delete_entity(self, project_id: str, entity_id: str) -> bool:
        """软删（人工删除，Dashboard）；关联关系随查询自动过滤（端点不在 active 集）。"""
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "UPDATE onto_entities SET status='deleted', last_seen=? "
                "WHERE project_id=? AND id=? AND status='active'",
                (_now(), project_id, entity_id),
            )
            return cur.rowcount > 0

    def mark_extracted(self, project_id: str, doc_ref: str) -> None:
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO onto_extracted_docs VALUES (?,?,?)", (project_id, doc_ref, _now()))

    def is_extracted(self, project_id: str, doc_ref: str) -> bool:
        with self._conn() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM onto_extracted_docs WHERE project_id=? AND doc_ref=?", (project_id, doc_ref)
                ).fetchone()
                is not None
            )

    def stats(self, project_id: str) -> dict:
        g = self.get_graph(project_id)
        payload = g.to_payload()
        with self._conn() as conn:
            docs = conn.execute(
                "SELECT COUNT(*) c FROM onto_extracted_docs WHERE project_id=?", (project_id,)
            ).fetchone()["c"]
        payload["stats"]["extracted_docs"] = docs
        return payload["stats"]

    # ---------------------------------------------------------------- 衍生
    def get_mermaid(self, project_id: str, max_nodes: int = 200) -> str:
        g = self.get_graph(project_id)
        ents = g.entities[:max_nodes]
        ent_ids = {e.id for e in ents}
        rels = [r for r in g.relations if r.from_entity in ent_ids and r.to_entity in ent_ids]

        def esc(text: str) -> str:
            return text.replace('"', "'").replace("<", "(").replace(">", ")")

        lines = ["graph LR"]
        for e in ents:
            lines.append(f'  n{e.id}["{esc(e.name)}<br/>{esc(e.type)}"]')
        for r in rels:
            lines.append(f'  n{r.from_entity} -->|"{esc(r.relation_type)}"| n{r.to_entity}')
        if len(g.entities) > max_nodes:
            lines.append(f"  %% 截断保护：共 {len(g.entities)} 实体，仅渲染前 {max_nodes}")
        return "\n".join(lines) + "\n"

    def get_summary(self, project_id: str, max_chars: int = 2500) -> str:
        """本体图压缩摘要（注入 research prompt 用，13 号 §3.2 business_model_summary）。"""
        g = self.get_graph(project_id)
        if not g.entities:
            return "（本体为空：尚未抽取）"
        by_type: dict[str, list[str]] = {}
        for e in g.entities:
            by_type.setdefault(e.type, []).append(e.name)
        parts = [f"# 业务本体摘要（{len(g.entities)} 实体 / {len(g.relations)} 关系 / {len(g.rules)} 规则）"]
        for etype, names in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
            shown = "、".join(names[:8]) + ("…" if len(names) > 8 else "")
            parts.append(f"- {etype}({len(names)}): {shown}")
        if g.relations:
            rel_types: dict[str, int] = {}
            for r in g.relations:
                rel_types[r.relation_type] = rel_types.get(r.relation_type, 0) + 1
            dist = "、".join(f"{k}×{v}" for k, v in sorted(rel_types.items(), key=lambda kv: -kv[1])[:6])
            parts.append(f"关系分布: {dist}")
        for rule in sorted(g.rules, key=lambda r: -r.confidence)[:5]:
            src = f"（来源 {rule.source_docs[0]}）" if rule.source_docs else ""
            parts.append(f"- 规则: IF {rule.condition} THEN {rule.conclusion} {src}")
        text = "\n".join(parts)
        return text[:max_chars]

    def annotate_hints(self, project_id: str, content: str, title: str = "", limit: int = 20) -> list[str]:
        """entity_hints 预标注：active 实体名/别名在文档中出现即命中（知识库 ingest metadata）。"""
        text = f"{title}\n{content}".lower()
        hits: list[str] = []
        for r in self._entity_rows(project_id):
            names = [r["name"], *json.loads(r["properties"]).get("aliases", [])]
            if any(n and n.lower() in text for n in names):
                hits.append(r["name"])
                if len(hits) >= limit:
                    break
        return hits

    def health(self) -> dict:
        return {"status": "ok", "service": "ontology", "version": "embedded-0.4.0"}
