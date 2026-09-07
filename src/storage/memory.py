"""
内存存储实现 - 测试与演示用（STORAGE_PROVIDER=memory）
行为与 v0.1.0 的模块级 dict 完全一致，保证 330 个既有测试不破坏
"""

from __future__ import annotations

import copy
import threading
from typing import Optional

from .base import StorageProvider


class MemoryStorage(StorageProvider):
    """内存实现：dict 容器 + 浅拷贝防护"""

    def __init__(self) -> None:
        self._projects: dict[str, dict] = {}
        self._documents: dict[str, list[dict]] = {}
        self._tasks: dict[str, dict] = {}
        self._benchmarks: dict[str, dict] = {}
        self._reviews: list[dict] = []
        self._feedback: dict[str, list[dict]] = {}
        self._lock = threading.RLock()

    # ===== 项目 =====
    def create_project(self, project: dict) -> None:
        with self._lock:
            self._projects[project["id"]] = copy.deepcopy(project)

    def get_project(self, project_id: str) -> Optional[dict]:
        with self._lock:
            p = self._projects.get(project_id)
            return copy.deepcopy(p) if p else None

    def list_projects(self) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(p) for p in self._projects.values()]

    def update_project(self, project_id: str, fields: dict) -> Optional[dict]:
        with self._lock:
            p = self._projects.get(project_id)
            if p is None:
                return None
            p.update(copy.deepcopy(fields))
            return copy.deepcopy(p)

    # ===== 文档 =====
    def add_document(self, project_id: str, doc: dict) -> None:
        with self._lock:
            self._documents.setdefault(project_id, []).append(copy.deepcopy(doc))

    def list_documents(self, project_id: str) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(d) for d in self._documents.get(project_id, [])]

    # ===== 任务 =====
    @staticmethod
    def _task_key(task: dict) -> str:
        return task.get("id") or task.get("task_id") or ""

    def create_task(self, task: dict) -> None:
        with self._lock:
            self._tasks[self._task_key(task)] = copy.deepcopy(task)

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            t = self._tasks.get(task_id)
            return copy.deepcopy(t) if t else None

    def update_task(self, task_id: str, fields: dict) -> Optional[dict]:
        with self._lock:
            t = self._tasks.get(task_id)
            if t is None:
                return None
            t.update(copy.deepcopy(fields))
            return copy.deepcopy(t)

    def list_tasks(self, project_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
        if project_id is not None:
            tasks = [t for t in tasks if t.get("project_id") == project_id]
        return [copy.deepcopy(t) for t in tasks]

    # ===== Benchmark =====
    def save_benchmark(self, benchmark: dict) -> None:
        with self._lock:
            self._benchmarks[benchmark["benchmark_id"]] = copy.deepcopy(benchmark)

    def get_benchmark(self, benchmark_id: str) -> Optional[dict]:
        with self._lock:
            bm = self._benchmarks.get(benchmark_id)
            return copy.deepcopy(bm) if bm else None

    def list_benchmarks(self, project_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            bms = list(self._benchmarks.values())
        if project_id is not None:
            bms = [b for b in bms if b.get("project_id") == project_id]
        return [copy.deepcopy(b) for b in bms]

    # ===== 审核 =====
    def add_review(self, review: dict) -> dict:
        with self._lock:
            stored = copy.deepcopy(review)
            self._reviews.append(stored)
            return copy.deepcopy(stored)

    def get_review(self, review_id: str) -> Optional[dict]:
        with self._lock:
            for r in self._reviews:
                if r.get("review_id") == review_id:
                    return copy.deepcopy(r)
        return None

    def list_reviews(self, status: Optional[str] = None) -> list[dict]:
        with self._lock:
            reviews = list(self._reviews)
        if status is not None:
            reviews = [r for r in reviews if r.get("status") == status]
        return [copy.deepcopy(r) for r in reviews]

    def update_review(self, review_id: str, fields: dict) -> Optional[dict]:
        with self._lock:
            for r in self._reviews:
                if r.get("review_id") == review_id:
                    r.update(copy.deepcopy(fields))
                    return copy.deepcopy(r)
        return None

    # ===== 反馈 =====
    def add_feedback(self, project_id: str, feedback: dict) -> None:
        with self._lock:
            self._feedback.setdefault(project_id, []).append(copy.deepcopy(feedback))

    def list_feedback(self, project_id: str) -> list[dict]:
        with self._lock:
            return [copy.deepcopy(f) for f in self._feedback.get(project_id, [])]

    # ===== 统计 =====
    def count_running_tasks(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.get("status") == "running")
