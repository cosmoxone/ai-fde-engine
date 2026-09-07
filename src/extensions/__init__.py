"""
商业扩展点 - TE/EE 功能挂载接口（v0.1.1 A5 预留）

设计原则（见 docs/09-后续规划.md §5.2）：
- 开源仓库保持纯净：只提供接口与 CE 默认实现
- 商业版（ai-fde-team 包）安装后调用 register() 注入能力
- AIFDE_EDITION 环境变量 / registry 状态决定 Dashboard 能力开关

提供的扩展点：
- plugin_registry : 通用插件注册器（本文件）
- auth_provider   : 认证与权限抽象（auth.py，CE 默认放行）
- storage_provider: 存储抽象（src/storage/，CE 默认 SQLite）
- template_source : 模板源抽象（v0.1.2 B2 行业模板时启用）
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class PluginInfo:
    """已注册插件元数据"""

    name: str
    version: str
    description: str = ""
    provider: str = "community"  # community / team / enterprise
    hooks: dict[str, Callable] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)  # 解锁的界面能力标识


class PluginRegistry:
    """
    插件注册器

    用法（商业包安装时）：
        from src.extensions import get_registry
        registry.register(PluginInfo(
            name="team-edition", version="1.0.0",
            provider="team",
            capabilities=["multi_user", "team_memory", "rbac"],
        ))
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._lock = threading.RLock()

    def register(self, plugin: PluginInfo) -> None:
        """注册插件；重名抛 ValueError（防止静默覆盖）"""
        with self._lock:
            if plugin.name in self._plugins:
                raise ValueError(f"插件已注册: {plugin.name}")
            self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._plugins.pop(name, None) is not None

    def get(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginInfo]:
        with self._lock:
            return list(self._plugins.values())

    def has_capability(self, capability: str) -> bool:
        """判断某能力是否已解锁（Dashboard 据此显隐界面）"""
        with self._lock:
            return any(capability in p.capabilities for p in self._plugins.values())

    @property
    def edition(self) -> str:
        """当前版本标识：community / team / enterprise"""
        with self._lock:
            providers = {p.provider for p in self._plugins.values()}
            if "enterprise" in providers:
                return "enterprise"
            if "team" in providers:
                return "team"
            return "community"


_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """获取全局插件注册器单例"""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_registry() -> None:
    """重置注册器（测试用）"""
    global _registry
    _registry = None
