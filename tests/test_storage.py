"""
存储层契约测试（v0.1.1 A1）

对 MemoryStorage 与 SQLiteStorage 跑同一套契约用例，
保证两个实现行为一致（替换后端时契约不破）。
另含：SQLite 重启持久化验证（单机核心价值）。
"""

from __future__ import annotations

import pytest

from src.storage.base import StorageProvider
from src.storage.memory import MemoryStorage
from src.storage.sqlite import SQLiteStorage


def _sample_project(pid: str = "p1") -> dict:
    return {
        "id": pid,
        "name": "智能质检知识库",
        "client_name": "华宇精密",
        "status": "research",
        "created_at": 1700000000.0,
        "config": {"industry": "manufacturing"},
        "requirements_baseline": None,
    }


@pytest.fixture(params=["memory", "sqlite"])
def storage(request, tmp_path) -> StorageProvider:
    """参数化：两种实现跑同一契约"""
    if request.param == "memory":
        return MemoryStorage()
    return SQLiteStorage(data_dir=str(tmp_path / "data"))


# ===== 契约用例（两种实现共同通过）=====


class TestProjectContract:
    def test_create_and_get(self, storage):
        project = _sample_project()
        storage.create_project(project)
        got = storage.get_project("p1")
        assert got is not None
        assert got["name"] == "智能质检知识库"
        assert got["config"]["industry"] == "manufacturing"

    def test_get_missing_returns_none(self, storage):
        assert storage.get_project("nope") is None

    def test_list_projects(self, storage):
        storage.create_project(_sample_project("p1"))
        storage.create_project(_sample_project("p2"))
        ids = {p["id"] for p in storage.list_projects()}
        assert ids == {"p1", "p2"}

    def test_update_fields(self, storage):
        storage.create_project(_sample_project())
        updated = storage.update_project("p1", {"status": "design", "requirements_baseline": {"requirements": []}})
        assert updated["status"] == "design"
        assert updated["name"] == "智能质检知识库"  # 未指定字段保留
        assert storage.get_project("p1")["requirements_baseline"]["requirements"] == []

    def test_update_missing_returns_none(self, storage):
        assert storage.update_project("nope", {"status": "x"}) is None

    def test_nested_dict_roundtrip(self, storage):
        """嵌套结构（Agent structured_output）无损往返"""
        project = _sample_project()
        project["solutions"] = {
            "tech_solution": {"modules": ["kb", "chat"], "estimates": {"days": 10}},
            "alternatives": [{"name": f"方案{i}", "score": i / 10} for i in range(3)],
        }
        storage.create_project(project)
        got = storage.get_project("p1")
        assert got["solutions"]["tech_solution"]["modules"] == ["kb", "chat"]
        assert len(got["solutions"]["alternatives"]) == 3
        assert got["solutions"]["alternatives"][2]["score"] == 0.2


class TestDocumentContract:
    def test_add_and_list_order(self, storage):
        storage.create_project(_sample_project())
        for i in range(3):
            storage.add_document("p1", {"filename": f"doc{i}.md", "content": f"内容{i}", "pages": i + 1})
        docs = storage.list_documents("p1")
        assert [d["filename"] for d in docs] == ["doc0.md", "doc1.md", "doc2.md"]

    def test_list_missing_project_empty(self, storage):
        assert storage.list_documents("nope") == []


class TestTaskContract:
    def test_create_with_id_key(self, storage):
        storage.create_task({"id": "t1", "project_id": "p1", "status": "running", "type": "research"})
        task = storage.get_task("t1")
        assert task["status"] == "running"

    def test_create_with_task_id_key(self, storage):
        """self-service 模块用 task_id 作为主键的兼容性"""
        storage.create_task({"task_id": "t2", "status": "running", "type": "identify_opportunities"})
        assert storage.get_task("t2")["type"] == "identify_opportunities"

    def test_update(self, storage):
        storage.create_task({"id": "t1", "status": "running"})
        updated = storage.update_task("t1", {"status": "completed", "result": {"accuracy": 0.9}})
        assert updated["status"] == "completed"
        assert storage.get_task("t1")["result"]["accuracy"] == 0.9

    def test_list_by_project(self, storage):
        storage.create_task({"id": "t1", "project_id": "p1", "status": "completed"})
        storage.create_task({"id": "t2", "project_id": "p2", "status": "completed"})
        storage.create_task({"id": "t3", "project_id": "p1", "status": "running"})
        assert len(storage.list_tasks("p1")) == 2
        assert len(storage.list_tasks()) == 3

    def test_count_running(self, storage):
        storage.create_task({"id": "t1", "status": "running"})
        storage.create_task({"id": "t2", "status": "running"})
        storage.create_task({"id": "t3", "status": "completed"})
        assert storage.count_running_tasks() == 2


class TestBenchmarkContract:
    def test_save_get_list(self, storage):
        storage.save_benchmark({"benchmark_id": "bm1", "project_id": "p1", "case_count": 50, "test_cases": []})
        storage.save_benchmark({"benchmark_id": "bm2", "project_id": "p2", "case_count": 30, "test_cases": []})
        assert storage.get_benchmark("bm1")["case_count"] == 50
        assert storage.get_benchmark("nope") is None
        assert len(storage.list_benchmarks("p1")) == 1

    def test_save_overwrites(self, storage):
        storage.save_benchmark({"benchmark_id": "bm1", "case_count": 10})
        storage.save_benchmark({"benchmark_id": "bm1", "case_count": 99})
        assert storage.get_benchmark("bm1")["case_count"] == 99


class TestReviewContract:
    def _review(self, rid: str = "rev-1") -> dict:
        return {"review_id": rid, "project_id": "p1", "status": "pending", "result": {"ok": True}}

    def test_add_list_filter(self, storage):
        storage.add_review(self._review("rev-1"))
        storage.add_review(self._review("rev-2"))
        assert len(storage.list_reviews()) == 2
        assert len(storage.list_reviews(status="pending")) == 2

    def test_update_status(self, storage):
        storage.add_review(self._review("rev-1"))
        updated = storage.update_review("rev-1", {"status": "approved", "comment": "通过", "reviewer": "fde-1"})
        assert updated["status"] == "approved"
        assert updated["comment"] == "通过"
        assert len(storage.list_reviews(status="pending")) == 0
        assert storage.update_review("nope", {}) is None


class TestFeedbackContract:
    def test_add_list(self, storage):
        storage.add_feedback("p1", {"score": 4, "comment": "很好用"})
        storage.add_feedback("p1", {"score": 5, "comment": "效率翻倍"})
        feedback = storage.list_feedback("p1")
        assert len(feedback) == 2
        assert feedback[1]["comment"] == "效率翻倍"
        assert storage.list_feedback("nope") == []


# ===== SQLite 专属：持久化与工厂 =====


class TestSQLitePersistence:
    def test_restart_preserves_data(self, tmp_path):
        """核心价值验证：关闭（新实例）后数据仍在 = 应用重启不丢"""
        data_dir = str(tmp_path / "data")
        s1 = SQLiteStorage(data_dir=data_dir)
        s1.create_project(_sample_project())
        s1.create_task({"id": "t1", "project_id": "p1", "status": "completed", "result": {"acc": 0.9}})
        s1.add_review({"review_id": "rev-1", "status": "pending"})
        s1.add_document("p1", {"filename": "a.md"})
        s1.add_feedback("p1", {"score": 5})
        s1.save_benchmark({"benchmark_id": "bm1", "project_id": "p1"})

        s2 = SQLiteStorage(data_dir=data_dir)  # 模拟重启
        assert s2.get_project("p1")["name"] == "智能质检知识库"
        assert s2.get_task("t1")["result"]["acc"] == 0.9
        assert s2.get_review("rev-1")["status"] == "pending"
        assert len(s2.list_documents("p1")) == 1
        assert len(s2.list_feedback("p1")) == 1
        assert s2.get_benchmark("bm1") is not None

    def test_concurrent_writes_thread_safe(self, tmp_path):
        """BackgroundTasks 跨线程写入不损坏"""
        import threading

        s = SQLiteStorage(data_dir=str(tmp_path / "data"))
        errors = []

        def writer(n: int):
            try:
                for i in range(20):
                    s.create_task({"id": f"t{n}-{i}", "status": "completed", "seq": i})
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert not errors
        assert len(s.list_tasks()) == 80


class TestStorageFactory:
    def test_factory_memory(self, monkeypatch):
        from src.storage import get_storage, reset_storage

        monkeypatch.setenv("STORAGE_PROVIDER", "memory")
        reset_storage()
        assert type(get_storage()).__name__ == "MemoryStorage"
        reset_storage()

    def test_factory_sqlite(self, monkeypatch, tmp_path):
        from src.storage import get_storage, reset_storage

        monkeypatch.setenv("STORAGE_PROVIDER", "sqlite")
        monkeypatch.setenv("AIFDE_DATA_DIR", str(tmp_path / "d"))
        reset_storage()
        assert type(get_storage()).__name__ == "SQLiteStorage"
        reset_storage()

    def test_factory_unknown_raises(self, monkeypatch):
        from src.storage import get_storage, reset_storage

        monkeypatch.setenv("STORAGE_PROVIDER", "cassandra")
        reset_storage()
        with pytest.raises(ValueError, match="cassandra"):
            get_storage()
        reset_storage()
