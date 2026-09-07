"""
SQLite 存储实现 - CE 默认后端（STORAGE_PROVIDER=sqlite，默认）

设计要点：
- 单文件 data/aifde.db，WAL 模式，零服务依赖（单机开箱即用核心）
- 每操作短连接：规避线程问题（BackgroundTasks 跨线程），单机写入频率低
- 实体存 JSON 文本列：存储层不做 schema 迁移，实体结构演进零成本
- TE 商业版可基于本模块替换为 PostgreSQL（接口契约见 base.py）
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Optional

from .base import StorageProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS documents (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE TABLE IF NOT EXISTS benchmarks (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_benchmarks_project ON benchmarks(project_id);
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    project_id TEXT,
    status TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_project ON feedback(project_id);
"""


def _task_key(task: dict) -> str:
    return task.get("id") or task.get("task_id") or ""


class SQLiteStorage(StorageProvider):
    """SQLite 单文件实现"""

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = data_dir
        self._db_path = os.path.join(data_dir, "aifde.db")
        self._init_lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._init_lock, self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ===== 内部工具 =====
    @staticmethod
    def _dump(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)

    @staticmethod
    def _load(text: str) -> dict:
        return json.loads(text)

    def _get_row(self, table: str, key_col: str, key: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(f"SELECT data FROM {table} WHERE {key_col} = ?", (key,)).fetchone()
        return self._load(row["data"]) if row else None

    def _upsert(self, table: str, key_col: str, key: str, entity: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({key_col}, data) VALUES (?, ?)",
                (key, self._dump(entity)),
            )

    def _update_fields(self, table: str, key_col: str, key: str, fields: dict) -> Optional[dict]:
        entity = self._get_row(table, key_col, key)
        if entity is None:
            return None
        entity.update(fields)
        self._upsert(table, key_col, key, entity)
        return entity

    # ===== 项目 =====
    def create_project(self, project: dict) -> None:
        self._upsert("projects", "id", project["id"], project)

    def get_project(self, project_id: str) -> Optional[dict]:
        return self._get_row("projects", "id", project_id)

    def list_projects(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT data FROM projects ORDER BY created_at, id").fetchall()
        return [self._load(r["data"]) for r in rows]

    def update_project(self, project_id: str, fields: dict) -> Optional[dict]:
        return self._update_fields("projects", "id", project_id, fields)

    # ===== 文档 =====
    def add_document(self, project_id: str, doc: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO documents (project_id, data) VALUES (?, ?)",
                (project_id, self._dump(doc)),
            )

    def list_documents(self, project_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM documents WHERE project_id = ? ORDER BY seq",
                (project_id,),
            ).fetchall()
        return [self._load(r["data"]) for r in rows]

    # ===== 任务 =====
    def create_task(self, task: dict) -> None:
        task_id = _task_key(task)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tasks (id, project_id, data) VALUES (?, ?, ?)",
                (task_id, task.get("project_id"), self._dump(task)),
            )

    def get_task(self, task_id: str) -> Optional[dict]:
        return self._get_row("tasks", "id", task_id)

    def update_task(self, task_id: str, fields: dict) -> Optional[dict]:
        return self._update_fields("tasks", "id", task_id, fields)

    def list_tasks(self, project_id: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if project_id is None:
                rows = conn.execute("SELECT data FROM tasks").fetchall()
            else:
                rows = conn.execute("SELECT data FROM tasks WHERE project_id = ?", (project_id,)).fetchall()
        return [self._load(r["data"]) for r in rows]

    # ===== Benchmark =====
    def save_benchmark(self, benchmark: dict) -> None:
        bid = benchmark["benchmark_id"]
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO benchmarks (id, project_id, data) VALUES (?, ?, ?)",
                (bid, benchmark.get("project_id"), self._dump(benchmark)),
            )

    def get_benchmark(self, benchmark_id: str) -> Optional[dict]:
        return self._get_row("benchmarks", "id", benchmark_id)

    def list_benchmarks(self, project_id: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if project_id is None:
                rows = conn.execute("SELECT data FROM benchmarks").fetchall()
            else:
                rows = conn.execute("SELECT data FROM benchmarks WHERE project_id = ?", (project_id,)).fetchall()
        return [self._load(r["data"]) for r in rows]

    # ===== 审核 =====
    def add_review(self, review: dict) -> dict:
        rid = review.get("review_id") or ""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO reviews (review_id, project_id, status, data) VALUES (?, ?, ?, ?)",
                (rid, review.get("project_id"), review.get("status"), self._dump(review)),
            )
        return review

    def get_review(self, review_id: str) -> Optional[dict]:
        return self._get_row("reviews", "review_id", review_id)

    def list_reviews(self, status: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if status is None:
                rows = conn.execute("SELECT data FROM reviews").fetchall()
            else:
                rows = conn.execute("SELECT data FROM reviews WHERE status = ?", (status,)).fetchall()
        return [self._load(r["data"]) for r in rows]

    def update_review(self, review_id: str, fields: dict) -> Optional[dict]:
        entity = self._get_row("reviews", "review_id", review_id)
        if entity is None:
            return None
        entity.update(fields)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO reviews (review_id, project_id, status, data) VALUES (?, ?, ?, ?)",
                (
                    review_id,
                    entity.get("project_id"),
                    entity.get("status"),
                    self._dump(entity),
                ),
            )
        return entity

    # ===== 反馈 =====
    def add_feedback(self, project_id: str, feedback: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO feedback (project_id, data) VALUES (?, ?)",
                (project_id, self._dump(feedback)),
            )

    def list_feedback(self, project_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT data FROM feedback WHERE project_id = ? ORDER BY seq",
                (project_id,),
            ).fetchall()
        return [self._load(r["data"]) for r in rows]

    # ===== 统计 =====
    def count_running_tasks(self) -> int:
        with self._conn() as conn:
            rows = conn.execute("SELECT data FROM tasks").fetchall()
        return sum(1 for r in rows if self._load(r["data"]).get("status") == "running")
