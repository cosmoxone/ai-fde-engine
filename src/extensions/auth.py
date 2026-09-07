"""
认证扩展点 - CE 默认无认证，TE 商业版注入 JWT+RBAC（v0.1.1 A5 预留）

CE（本仓库）：NoopAuth 放行一切请求 —— 单机本机使用定位
TE（ai-fde-team 包）：实现本接口注册 JWT 认证 + 四级 RBAC
（权限矩阵定义见 docs/01-需求文档.md §4.3.2）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, Request


@dataclass
class Principal:
    """认证主体（请求方身份）"""

    user_id: str = "anonymous"
    role: str = "fde"  # admin / manager / fde / client
    permissions: list[str] = None  # type: ignore[assignment]

    def has_permission(self, permission: str) -> bool:
        return permission in (self.permissions or [])


class AuthProvider(ABC):
    """认证提供方抽象"""

    @abstractmethod
    async def authenticate(self, request: Request) -> Optional[Principal]:
        """
        从请求解析身份；匿名/非法返回 None
        返回 None 时的处理策略由 allow_anonymous 决定
        """

    @property
    @abstractmethod
    def allow_anonymous(self) -> bool:
        """是否允许匿名访问（CE=True 放行，TE=False 拒绝）"""

    @abstractmethod
    def register_middleware(self, app: FastAPI) -> None:
        """将认证逻辑挂载为 FastAPI 中间件"""


class NoopAuth(AuthProvider):
    """CE 默认实现：不做任何认证（单机本机使用）"""

    async def authenticate(self, request: Request) -> Optional[Principal]:
        return Principal(user_id="local", role="admin", permissions=["*"])

    @property
    def allow_anonymous(self) -> bool:
        return True

    def register_middleware(self, app: FastAPI) -> None:
        """CE 版无中间件需要挂载（保持零开销）"""
        return None


def get_auth_provider() -> AuthProvider:
    """
    获取认证提供方：
    - 商业包注册了自定义 provider 则返回之
    - 否则返回 CE 默认 NoopAuth
    """
    from . import get_registry

    registry = get_registry()
    for plugin in registry.list_plugins():
        auth = plugin.hooks.get("auth_provider")
        if isinstance(auth, AuthProvider):
            return auth
    return NoopAuth()
