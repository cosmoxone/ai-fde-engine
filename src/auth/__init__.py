"""认证模块（CE v0.5）——AuthProvider 替换点 + LocalAuthProvider 默认实现。

装配（优先级从高到低）：
1. `set_auth_provider(p)` 装配期显式注入（TE/EE 装配入口、测试用）
2. `AUTH_PROVIDER=<name>` 环境选择：local（默认）｜经 `register_auth_provider` 注册的外部名
   （TE/EE 商业包装配时注册 casdoor 等，内核仅见协议、零感知实现——设计 25/27 号）
3. 未注册的外部名 → 回落 local 单用户档（既有行为，附运维提示）
"""

from __future__ import annotations

from typing import Callable

from .local import LocalAuthProvider, hash_password, verify_password
from .provider import AuthProvider, User

__all__ = [
    "AuthProvider",
    "User",
    "LocalAuthProvider",
    "hash_password",
    "verify_password",
    "register_auth_provider",
    "get_provider_factory",
    "registered_providers",
    "set_auth_provider",
    "get_auth_provider",
    "reset_auth_provider",
]

_provider: AuthProvider | None = None
"""进程级单例（set_auth_provider 注入或首次 get_auth_provider 按设置装配）。"""

# 替换 provider 注册表（进程级）：name → 工厂。商业包（ee 层）装配时注册，内核不 import 任何实现。
ProviderFactory = Callable[[], AuthProvider]
_EXTERNAL_PROVIDERS: dict[str, ProviderFactory] = {}


def register_auth_provider(name: str, factory: ProviderFactory) -> None:
    """注册替换认证提供方工厂（如 ee 层 casdoor）。同名覆盖（测试隔离/升级替换）。"""
    _EXTERNAL_PROVIDERS[name.lower()] = factory


def get_provider_factory(name: str) -> ProviderFactory | None:
    """按名取注册的工厂；未注册返回 None。"""
    return _EXTERNAL_PROVIDERS.get((name or "").strip().lower())


def registered_providers() -> tuple[str, ...]:
    """当前已注册的替换 provider 名单（供装配层校验与报错提示）。"""
    return tuple(sorted(_EXTERNAL_PROVIDERS))


def set_auth_provider(provider: AuthProvider) -> None:
    """装配期注入 provider 单例（TE/EE 装配入口用；测试亦用）。与 AUTH_PROVIDER 环境装配二选一。"""
    global _provider
    _provider = provider


def get_auth_provider() -> AuthProvider:
    """进程级单例：注入优先，其次按 settings 装配；替换 provider 经 AUTH_PROVIDER 选择（TE 场景）。"""
    global _provider
    if _provider is None:
        from ..config import get_settings

        s = get_settings()
        name = (s.auth_provider or "local").strip().lower()
        if name == "local":
            _provider = LocalAuthProvider(
                users_enabled=bool(s.local_users_enabled),
                data_dir=s.data_dir,
                admin_invite_code=s.admin_invite_code,
            )
        elif (factory := get_provider_factory(name)) is not None:
            _provider = factory()  # 替换点：外部注册 provider（如 ee 层 casdoor）整块接管
        else:  # 选了外部名但未注册——回落 local 单用户档，并提示运维（避免无感降级）
            print(
                f"[auth] AUTH_PROVIDER={name} 未注册（可用：local"
                f"{'、' + '、'.join(registered_providers()) if registered_providers() else ''}），回落 local 单用户档"
            )
            _provider = LocalAuthProvider(users_enabled=False, data_dir=s.data_dir)
    return _provider


def reset_auth_provider() -> None:
    """测试隔离用（清空注入与单例；不动注册表）。"""
    global _provider
    _provider = None
