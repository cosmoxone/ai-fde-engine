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
        """路由结构固定（10 条：6 登录面 + 4 成员管理，导入时挂载一次）；单用户档 /login 返回无需登录提示。"""
        assert len(LocalAuthProvider(users_enabled=False, data_dir="/tmp").login_routes().routes) == 10

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
            # P-5 回归：JS 不得残留 format 转义双大括号（浏览器 SyntaxError，登录按钮失效）
            assert "function go(){" in html
            assert "function v(id){" in html
            # 首登分支回归：login 对未注册用户返回 401（非 403），前端据此转 activate
            assert "(r.status===401||r.status===403)" in html


class TestAdminUserManagement:
    """二阶段：成员管理端点矩阵（/auth/users*，仅 admin）。"""

    @pytest.fixture()
    def provider(self, tmp_path):
        return LocalAuthProvider(users_enabled=True, data_dir=str(tmp_path), admin_invite_code="ADMIN-CODE-1")

    @staticmethod
    def _setup_team(provider):
        """激活 boss(admin) 并直接造一个 member bob，返回 (bob_id, invite)。"""
        with _authd_client(provider) as c:
            r = c.post(
                "/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "ADMIN-CODE-1"}
            )
            assert r.status_code == 200
            invite = c.post("/api/v1/auth/invites").json()["invite_code"]
        provider._conn.execute(
            "INSERT INTO local_users(id,name,pass_hash,platform_role) VALUES('u-bob','bob',?,'member')",
            (hash_password("bob-12345"),),
        )
        provider._conn.commit()
        return "u-bob", invite

    def test_users_list_admin_only(self, provider):
        _, _ = self._setup_team(provider)
        with _authd_client(provider) as c:
            assert c.get("/api/v1/auth/users").status_code == 401  # 未登录
        # bob（member）登录后 403
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"})
            assert c.get("/api/v1/auth/users").status_code == 403
        # boss（admin）可见两名用户与角色
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            r = c.get("/api/v1/auth/users")
            assert r.status_code == 200
            names = {u["name"]: u for u in r.json()["users"]}
            assert set(names) == {"boss", "bob"}
            assert names["bob"]["platform_role"] == "member"

    def test_disable_user_blocks_login_and_session(self, provider):
        _, _ = self._setup_team(provider)
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            r = c.patch("/api/v1/auth/users/u-bob", json={"status": "disabled"})
            assert r.status_code == 200
        with _authd_client(provider) as c:
            assert c.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"}).status_code == 401
        # 启用恢复
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            c.patch("/api/v1/auth/users/u-bob", json={"status": "active"})
        with _authd_client(provider) as c:
            assert c.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"}).status_code == 200

    def test_cannot_lock_out_last_admin(self, provider):
        _, _ = self._setup_team(provider)
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            boss_id = c.get("/api/v1/auth/me").json()["user"]["id"]
            assert c.patch(f"/api/v1/auth/users/{boss_id}", json={"status": "disabled"}).status_code == 403
            assert c.patch(f"/api/v1/auth/users/{boss_id}", json={"platform_role": "member"}).status_code == 403

    def test_assign_and_remove_project_role(self, provider):
        _, _ = self._setup_team(provider)
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            # 非法角色/不存在用户
            assert c.put("/api/v1/auth/users/u-bob/projects/p1", json={"role": "hacker"}).status_code == 400
            assert c.put("/api/v1/auth/users/u-404/projects/p1", json={"role": "fde"}).status_code == 404
            # 分配 → me 里的 project_roles 生效；重复分配=改角色（upsert）
            assert c.put("/api/v1/auth/users/u-bob/projects/p1", json={"role": "fde"}).status_code == 200
            assert c.put("/api/v1/auth/users/u-bob/projects/p1", json={"role": "client_viewer"}).status_code == 200
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"})
            assert c.get("/api/v1/auth/me").json()["user"]["project_roles"] == {"p1": "client_viewer"}
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            assert c.delete("/api/v1/auth/users/u-bob/projects/p1").status_code == 200
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "bob", "password": "bob-12345"})
            assert c.get("/api/v1/auth/me").json()["user"]["project_roles"] == {}


class TestProjectOwnership:
    """二阶段：项目归属校验（guard + 列表过滤 + owner 自动授予）。多用户两用户互不可见。"""

    @pytest.fixture()
    def provider(self, tmp_path):
        return LocalAuthProvider(users_enabled=True, data_dir=str(tmp_path), admin_invite_code="ADMIN-CODE-1")

    def _client_as(self, provider, name, password):
        ctx = _authd_client(provider)
        return ctx, name, password

    def test_member_creates_and_isolation(self, provider):
        with _authd_client(provider) as c:  # boss(admin) 激活+邀请 bob
            c.post(
                "/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "ADMIN-CODE-1"}
            )
            invite = c.post("/api/v1/auth/invites").json()["invite_code"]
        with _authd_client(provider) as c:  # bob 激活并建项目
            c.post("/api/v1/auth/activate", json={"name": "bob", "password": "bob-12345", "invite_code": invite})
            r = c.post("/api/v1/projects", json={"name": "Bob 的项目", "client_name": "ACME"})
            assert r.status_code == 200
            pid = r.json()["project"]["id"]
            assert r.json()["project"]["owner_user_id"]  # 归属落档
            assert c.get(f"/api/v1/projects/{pid}").status_code == 200  # owner 自动授予→自己可见
            assert c.post(f"/api/v1/projects/{pid}/documents", json={"title": "x"}).status_code in (
                200,
                422,
            )  # 写权限在
        with _authd_client(provider) as c:  # boss 生成第二个邀请码
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            invite2 = c.post("/api/v1/auth/invites").json()["invite_code"]
        with _authd_client(provider) as c:  # carol 激活：对 bob 项目零可见
            r = c.post(
                "/api/v1/auth/activate", json={"name": "carol", "password": "carol-12345", "invite_code": invite2}
            )
            carol_id = r.json()["user_id"]
            names = [p["name"] for p in c.get("/api/v1/projects").json()["projects"]]
            assert names == []  # 列表过滤：非成员不可见
            assert c.get(f"/api/v1/projects/{pid}").status_code == 403  # guard：直接访问被拒
        with _authd_client(provider) as c:  # carol 被授 client_viewer：只读矩阵
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            assert (
                c.put(f"/api/v1/auth/users/{carol_id}/projects/{pid}", json={"role": "client_viewer"}).status_code
                == 200
            )
        with _authd_client(provider) as c:
            c.post("/api/v1/auth/login", json={"name": "carol", "password": "carol-12345"})
            assert c.get(f"/api/v1/projects/{pid}").status_code == 200  # read 放行
            assert c.get(f"/api/v1/projects/{pid}/documents").status_code == 200
            assert c.post(f"/api/v1/projects/{pid}/documents", json={"title": "hack"}).status_code == 403  # write 拒

    def test_admin_sees_all_and_single_user_unaffected(self, provider):
        with _authd_client(provider) as c:
            c.post(
                "/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "ADMIN-CODE-1"}
            )
            r = c.post("/api/v1/projects", json={"name": "P1"})
            pid = r.json()["project"]["id"]
        with _authd_client(provider) as c:  # 另一个 member 建的项目，admin 也能全量看到
            c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"})
            assert any(p["id"] == pid for p in c.get("/api/v1/projects").json()["projects"])
            assert c.get(f"/api/v1/projects/{pid}").status_code == 200
        # 单用户档：无 owner_user_id 字段、无过滤（v0.4 行为零变化）
        single = LocalAuthProvider(users_enabled=False, data_dir="/tmp")
        with _authd_client(single) as c:
            r = c.post("/api/v1/projects", json={"name": "单用户项目"})
            assert "owner_user_id" not in r.json()["project"]
            assert c.get("/api/v1/projects").json()["total"] >= 1


class _StubReplaceProvider:
    """替换点契约测试桩（25 号 §7）：模拟 casdoor 类外部 provider——
    头 X-User 承载身份、自带登录路由、独立的项目访问矩阵。"""

    users_enabled = True
    NAME = "stub"

    def __init__(self):
        from fastapi import APIRouter

        self._router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

        @self._router.get("/login")
        def login_page():
            from fastapi.responses import HTMLResponse

            return HTMLResponse("<h3>stub-login-page</h3>")

    def current_user(self, request):
        from fastapi import HTTPException

        from src.auth import User

        uid = request.headers.get("X-User", "")
        if not uid:
            raise HTTPException(status_code=401, detail="未登录(stub)")
        if uid == "boss":
            return User(id=uid, display_name=uid, platform_role="admin", project_roles={})
        return User(id=uid, display_name=uid, platform_role="member", project_roles={"p1": "fde"})

    def verify_project_access(self, user, project_id: str, action: str = "read") -> bool:
        return user.is_admin or project_id in user.project_roles

    def login_routes(self):
        return self._router


@pytest.fixture()
def patched_settings(monkeypatch):
    """provider 单例隔离 + settings 单例字段就地改写（monkeypatch 自动还原）。

    注意：**不得** get_settings.cache_clear()——清缓存会让 src.main 等模块导入时绑定的
    settings 引用孤儿化（save 改新单例、/health 读旧引用），污染后续测试模块。
    """
    from src.auth import reset_auth_provider

    reset_auth_provider()
    yield monkeypatch
    reset_auth_provider()


class TestProviderReplacement:
    """替换点契约（25 号 §7 验证口径）：注册→选择→整块替换后全端点仍通；未注册回落不裸奔。"""

    def test_register_and_env_selection(self, patched_settings):
        import src.auth as auth_mod
        from src.auth import get_auth_provider, registered_providers
        from src.config import get_settings

        calls: list[int] = []
        patched_settings.setattr(get_settings(), "auth_provider", "stub")
        auth_mod.register_auth_provider("stub", lambda: (calls.append(1), _StubReplaceProvider())[1])
        p = get_auth_provider()
        assert isinstance(p, _StubReplaceProvider) and calls == [1]
        assert get_auth_provider() is p  # 单例
        assert "stub" in registered_providers()

    def test_unregistered_name_falls_back_single_user(self, patched_settings, capsys):
        from src.auth import get_auth_provider
        from src.config import get_settings

        patched_settings.setattr(get_settings(), "auth_provider", "casdoor")
        p = get_auth_provider()
        assert isinstance(p, LocalAuthProvider) and not p.users_enabled  # 回落单用户档（既有行为）
        assert "未注册" in capsys.readouterr().out  # 但必须提示运维，不能无感降级

    def test_set_auth_provider_injection(self, patched_settings):
        import src.auth as auth_mod
        from src.auth import get_auth_provider

        stub = _StubReplaceProvider()
        auth_mod.set_auth_provider(stub)
        assert get_auth_provider() is stub  # 注入优先于环境装配

    def test_stub_provider_guards_honor_replacement(self, patched_settings):
        """运行时 guard 遵守替换 provider：未认证 401、项目矩阵/归属过滤照常（登录路由属装配期，见下）。"""
        stub = _StubReplaceProvider()
        with _authd_client(stub) as c:
            assert c.get("/api/v1/projects").status_code == 401  # guard 走 stub.current_user
            r = c.get("/api/v1/projects", headers={"X-User": "boss"})
            assert r.status_code == 200
            r = c.post("/api/v1/projects", json={"name": "P1"}, headers={"X-User": "boss"})
            pid = r.json()["project"]["id"]
            assert r.json()["project"]["owner_user_id"] == "boss"  # users_enabled=True → 归属落档
            assert c.get("/api/v1/projects", headers={"X-User": "alice"}).json()["total"] == 0
            assert c.get(f"/api/v1/projects/{pid}", headers={"X-User": "alice"}).status_code == 403
            assert c.get("/api/v1/projects/p1", headers={"X-User": "alice"}).status_code == 404  # 矩阵放行→业务 404

    def test_replacement_assembly_end_to_end(self, tmp_path):
        """整块替换契约（装配序）：先注入 provider 再导入 src.main——登录路由换血 + 全端点通。
        用子进程隔离（src.main 的 app/login 路由在进程内是装配期一次性挂载，须按真实装配序验证）。"""
        import os
        import subprocess
        import sys
        from pathlib import Path

        repo_root = str(Path(__file__).resolve().parents[1])
        env = {
            **os.environ,
            "PYTHONPATH": repo_root,
            "STORAGE_PROVIDER": "memory",
            "MEMORY_STORAGE_DIR": str(tmp_path / "memory"),
            "OPENHANDS_WORKSPACE_BASE": str(tmp_path / "ws"),
            "KNOWLEDGE_DB_PATH": str(tmp_path / "kb.db"),
            "ONTOLOGY_DB_PATH": str(tmp_path / "onto.db"),
            "DATA_DIR": str(tmp_path / "data"),
            "AUTH_PROVIDER": "stub",
        }
        os.makedirs(env["MEMORY_STORAGE_DIR"], exist_ok=True)
        os.makedirs(env["OPENHANDS_WORKSPACE_BASE"], exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "-c", _ASSEMBLY_PROBE], env=env, cwd=repo_root, capture_output=True, text=True, timeout=180
        )
        assert proc.returncode == 0 and "ASSEMBLY-OK" in proc.stdout, f"stdout={proc.stdout}\nstderr={proc.stderr}"

_ASSEMBLY_PROBE = """
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from src.auth import User, set_auth_provider


class Stub:
    users_enabled = True
    NAME = "stub"

    def __init__(self):
        r = APIRouter(prefix="/api/v1/auth")

        @r.get("/login")
        def lp():
            return HTMLResponse("<h3>stub-login-page</h3>")

        self._r = r

    def current_user(self, request):
        uid = request.headers.get("X-User", "")
        if not uid:
            raise HTTPException(401, "未登录(stub)")
        if uid == "boss":
            return User(id=uid, display_name=uid, platform_role="admin")
        return User(id=uid, display_name=uid, platform_role="member", project_roles={"p1": "fde"})

    def verify_project_access(self, user, project_id, action="read"):
        return user.is_admin or project_id in user.project_roles

    def login_routes(self):
        return self._r


set_auth_provider(Stub())  # 装配序：注入在前
from src.main import app  # noqa: E402 —— app/login 路由装配在后（登录路由来自替换 provider）

with TestClient(app) as c:
    assert "stub-login-page" in c.get("/api/v1/auth/login").text  # 登录路由已换血
    assert c.get("/api/v1/projects").status_code == 401
    r = c.post("/api/v1/projects", json={"name": "P1"}, headers={"X-User": "boss"})
    assert r.status_code == 200 and r.json()["project"]["owner_user_id"] == "boss"
    pid = r.json()["project"]["id"]
    assert c.get("/api/v1/projects", headers={"X-User": "alice"}).json()["total"] == 0
    assert c.get("/api/v1/projects/" + pid, headers={"X-User": "alice"}).status_code == 403
    assert c.get("/api/v1/projects/p1", headers={"X-User": "alice"}).status_code == 404
print("ASSEMBLY-OK")
"""
