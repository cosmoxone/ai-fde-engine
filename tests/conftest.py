"""
Pytest配置与共享fixture
"""

import os
import sys

import pytest

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """FastAPI TestClient（隔离存储环境由 autouse fixture 保证）"""
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


def _reset_gateways() -> None:
    """知识库/本体网关单例逐测试重置（模块未就绪不影响其余测试）。"""
    import importlib

    for mod_name, fn_name in (
        ("src.knowledge.gateway", "reset_knowledge_gateway"),
        ("src.ontology.gateway", "reset_ontology_gateway"),
    ):
        try:
            getattr(importlib.import_module(mod_name), fn_name)()
        except Exception:  # noqa: BLE001
            pass


@pytest.fixture(autouse=True)
def isolated_memory_dir(tmp_path):
    """每个测试使用独立的记忆存储目录 + 内存存储，避免测试间污染（v0.1.1 A1）"""
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path / "memory")
    os.environ["OPENHANDS_WORKSPACE_BASE"] = str(tmp_path / "workspace")
    os.environ["STORAGE_PROVIDER"] = "memory"  # 测试统一用内存存储（隔离且快速）
    os.makedirs(os.environ["MEMORY_STORAGE_DIR"], exist_ok=True)
    os.makedirs(os.environ["OPENHANDS_WORKSPACE_BASE"], exist_ok=True)
    os.environ["KNOWLEDGE_DB_PATH"] = str(tmp_path / "knowledge.db")  # 知识库 Embedded 隔离（v0.4-a）
    os.environ["ONTOLOGY_DB_PATH"] = str(tmp_path / "ontology.db")  # 本体 Embedded 隔离（v0.4-b）
    from src.storage import reset_storage

    reset_storage()
    _reset_gateways()
    yield
    # 清理MemoryManager单例
    from src.memory.manager import MemoryManager

    MemoryManager._instances.clear()
    reset_storage()
    _reset_gateways()
