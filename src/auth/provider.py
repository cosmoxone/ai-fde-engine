"""认证抽象（CE v0.5，设计 25 号 v1.1）。

AuthProvider 是 CE 的**可替换认证点**：
- 默认装配 LocalAuthProvider（local：单用户档/本地多用户档）
- TE/EE 以 CasdoorAuthProvider 整块替换（entry point 注册 `AUTH_PROVIDER=casdoor`），内核零感知

边界纪律（27 号判定规则）：本模块不含 OIDC/多租户/org——那些是 TE 特性（ee 层）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class User:
    """CE 用户语义（无租户字段——org 是 TE 特性）。"""

    id: str
    display_name: str = ""
    platform_role: str = "member"  # admin | member
    project_roles: dict[str, str] = field(default_factory=dict)  # {project_id: role}

    @property
    def is_admin(self) -> bool:
        return self.platform_role == "admin"


class AuthProvider(Protocol):
    """认证提供方接口（替换点）。实现方负责：用户识别、会话校验、项目访问判定、登录路由。"""

    def current_user(self, request) -> User:
        """从请求解析当前用户（未认证应抛 HTTPException 401）。"""
        ...

    def verify_project_access(self, user: User, project_id: str, action: str = "read") -> bool:
        """项目级访问判定（action: read|write|review）。"""
        ...

    def login_routes(self):
        """返回本 provider 的登录相关路由（可为空列表——如单用户档无登录页）。"""
        ...
