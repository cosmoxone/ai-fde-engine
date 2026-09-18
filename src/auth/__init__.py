"""认证模块（CE v0.5）——AuthProvider 替换点 + LocalAuthProvider 默认实现。

装配：AUTH_PROVIDER=local（默认）；TE/EE 注册 casdoor provider 整块替换（设计 25/27 号）。
"""

from __future__ import annotations

from .local import LocalAuthProvider, hash_password, verify_password
from .provider import AuthProvider, User

__all__ = ["AuthProvider", "User", "LocalAuthProvider", "hash_password", "verify_password"]


def get_auth_provider() -> LocalAuthProvider:
    """进程级单例（按 settings 装配；替换 provider 经 AUTH_PROVIDER 选择——TE 场景）。"""
    global _provider
    if _provider is None:
        from ..config import get_settings

        s = get_settings()
        if (s.auth_provider or "local").lower() == "local":
            _provider = LocalAuthProvider(
                users_enabled=bool(s.local_users_enabled),
                data_dir=s.data_dir,
                admin_invite_code=s.admin_invite_code,
            )
        else:  # 替换点：外部注册的 provider（如 ee 层 casdoor）；未注册时回落 local
            _provider = LocalAuthProvider(users_enabled=False, data_dir=s.data_dir)
    return _provider


def reset_auth_provider() -> None:
    """测试隔离用。"""
    global _provider
    _provider = None


_provider: LocalAuthProvider | None = None
