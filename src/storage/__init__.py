"""
存储层工厂 - 按 STORAGE_PROVIDER 配置选择实现（v0.1.1 A1/A5 扩展点）

用法：
    from src.storage import get_storage
    storage = get_storage()
    storage.create_project({...})

切换：
    STORAGE_PROVIDER=sqlite（默认，单文件 data/aifde.db）
    STORAGE_PROVIDER=memory（测试/演示）
"""

from __future__ import annotations

import os
from typing import Optional

from ..config import get_settings
from .base import StorageProvider
from .memory import MemoryStorage
from .sqlite import SQLiteStorage

_storage_instance: Optional[StorageProvider] = None


def get_storage() -> StorageProvider:
    """获取存储单例（线程安全懒加载）"""
    global _storage_instance
    if _storage_instance is None:
        provider = os.environ.get("STORAGE_PROVIDER", "") or get_settings().storage_provider
        if provider == "memory":
            _storage_instance = MemoryStorage()
        elif provider == "sqlite":
            settings = get_settings()
            _storage_instance = SQLiteStorage(data_dir=os.environ.get("AIFDE_DATA_DIR", settings.data_dir))
        else:
            raise ValueError(f"未知的 STORAGE_PROVIDER: {provider}（可选: memory/sqlite）")
    return _storage_instance


def reset_storage() -> None:
    """重置存储单例（测试用）"""
    global _storage_instance
    _storage_instance = None


__all__ = [
    "StorageProvider",
    "MemoryStorage",
    "SQLiteStorage",
    "get_storage",
    "reset_storage",
]
