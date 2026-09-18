"""认证模块测试（CE v0.5，设计 25 号 v1.1）。

验收口径：
- 单用户档（默认）：全部端点无 cookie 直通——v0.4 行为零变化
- 本地多用户档：激活管理员→登录→me→邀请码→成员激活→项目访问矩阵→未登录 401
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.auth import LocalAuthProvider, hash_password, verify_password


def _authd_client(provider):
    """以指定 provider 装配 app 的 TestClient（上下文管理器，自动恢复单例）。"""
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    import src.auth as auth_mod
    from src.auth import reset_auth_provider
    from src.main import app

    @contextmanager
    def _ctx():
        reset_auth_provider()
        auth_mod._provider = provider
        try:
            with TestClient(app) as c:
                yield c
        finally:
            reset_auth_provider()

    return _ctx()


class TestPasswordHash:
    def test_roundtrip_and_salt(self):
        h1 = hash_password("s3cret-pass")
        assert verify_password("s3cret-pass", h1)
        assert not verify_password("wrong", h1)
        assert hash_password("s3cret-pass") != h1  # 随机盐


class TestSingleUserMode:
    """单用户档：无登录面、全部端点直通（v0.4 零变化）。"""

    def test_provider_returns_builtin_admin(self):
        p = LocalAuthProvider(users_enabled=False, data_dir="/tmp")
        assert p.current_user(None).id == "local-admin"
        assert p.current_user(None).is_admin

    def test_login_routes_fixed_structure(self):
        """路由结构固定（6 条，导入时挂载一次）；单用户档 /login 返回无需登录提示。"""
        assert len(LocalAuthProvider(users_enabled=False, data_dir="/tmp").login_routes().routes) == 6

    def test_api_open_without_cookie(self):
        from src.main import app

        with TestClient(app) as c:
            r = c.get("/api/v1/health")
            assert r.status_code == 200
            r = c.get("/api/v1/projects")
            assert r.status_code == 200  # 无 cookie 直通（单用户档）


class TestLocalMultiUser:
    """本地多用户档：激活/登录/角色矩阵/未登录拒绝。"""

    @pytest.fixture()
    def provider(self, tmp_path):
        return LocalAuthProvider(users_enabled=True, data_dir=str(tmp_path), admin_invite_code="ADMIN-CODE-1")

    def test_full_flow(self, provider):
        with _authd_client(provider) as client:
            # ① 未登录：受保护端点 401，公开端点放行
            assert client.get("/api/v1/projects").status_code == 401
            assert client.get("/api/v1/health").status_code == 200
            assert client.get("/dashboard").status_code in (200, 307, 404)
            # ② 管理员激活（错误码→403）
            r = client.post(
                "/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "bad"}
            )
            assert r.status_code == 403
            r = client.post(
                "/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "ADMIN-CODE-1"}
            )
            assert r.status_code == 200 and r.json()["platform_role"] == "admin"
            # ③ 激活即登录（cookie 生效）
            assert client.get("/api/v1/auth/me").json()["user"]["display_name"] == "boss"
            assert client.get("/api/v1/projects").status_code == 200  # 管理员全通
            # ④ 邀请码：成员激活后可登录
            invite = client.post("/api/v1/auth/invites").json()["invite_code"]
        with _authd_client(provider) as c2:
            r = c2.post(
                "/api/v1/auth/activate", json={"name": "alice", "password": "alice-12345", "invite_code": invite}
            )
            assert r.status_code == 200 and r.json()["platform_role"] == "member"
            assert c2.get("/api/v1/projects").status_code == 200  # member 平台级可列项目

    def test_project_access_matrix(self, provider):
        u_admin = type("U", (), {"is_admin": True, "project_roles": {}})()
        assert provider.verify_project_access(u_admin, "p1", "write")

        fde = type("U", (), {"is_admin": False, "project_roles": {"p1": "fde"}})()
        assert provider.verify_project_access(fde, "p1", "write")
        assert not provider.verify_project_access(fde, "p2", "read")  # 非成员不可见

        expert = type("U", (), {"is_admin": False, "project_roles": {"p1": "domain_expert"}})()
        assert provider.verify_project_access(expert, "p1", "review")
        assert not provider.verify_project_access(expert, "p1", "write")  # 只读+审核

        viewer = type("U", (), {"is_admin": False, "project_roles": {"p1": "client_viewer"}})()
        assert provider.verify_project_access(viewer, "p1", "read")
        assert not provider.verify_project_access(viewer, "p1", "review")

    def test_login_logout(self, provider):
        provider._conn.execute(
            "INSERT INTO local_users(id,name,pass_hash,platform_role) VALUES('u1','bob',?, 'member')",
            (hash_password("bob-12345"),),
        )
        provider._conn.commit()
        with _authd_client(provider) as client:
            r = client.post("/api/v1/auth/login", json={"name": "bob", "password": "wrong"})
            assert r.status_code == 401
            r = client.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"})
            assert r.status_code == 200
            assert client.get("/api/v1/auth/me").json()["user"]["id"] == "u1"
            client.post("/api/v1/auth/logout")
            assert client.get("/api/v1/projects").status_code == 401

    def test_login_page_served(self, provider):
        with _authd_client(provider) as client:
            html = client.get("/api/v1/auth/login").text
            assert "管理员激活码" in html  # admin 未激活态
