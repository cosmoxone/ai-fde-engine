"""
Pytest配置与共享fixture
"""

import os
import sys

import pytest

# 确保项目根目录在Python路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolated_memory_dir(tmp_path):
    """每个测试使用独立的记忆存储目录 + 内存存储，避免测试间污染（v0.1.1 A1）"""
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path / "memory")
    os.environ["OPENHANDS_WORKSPACE_BASE"] = str(tmp_path / "workspace")
    os.environ["STORAGE_PROVIDER"] = "memory"  # 测试统一用内存存储（隔离且快速）
    os.makedirs(os.environ["MEMORY_STORAGE_DIR"], exist_ok=True)
    os.makedirs(os.environ["OPENHANDS_WORKSPACE_BASE"], exist_ok=True)
    from src.storage import reset_storage

    reset_storage()
    yield
    # 清理MemoryManager单例
    from src.memory.manager import MemoryManager

    MemoryManager._instances.clear()
    reset_storage()
