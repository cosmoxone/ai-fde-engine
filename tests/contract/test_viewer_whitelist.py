"""client_viewer 只读白名单契约测试（CE v0.5 二阶段，设计 25 号 §3.3）。

守护三件事：
1. 白名单由 OpenAPI 端点清单**自动生成**（viewer_whitelist 遍历 app.routes）——新端点零登记自动纳入；
2. 性质断言：全部 GET、全部项目作用域（含 {project_id}）、核心交付查看端点在列；
3. 与角色矩阵一致：client_viewer 对白名单路径 read 放行 / write 拒绝（guard 行为级验证）。
"""

from __future__ import annotations

from src.auth import LocalAuthProvider, reset_auth_provider
from src.auth.viewer import viewer_whitelist

# 核心交付查看端点（client_viewer 的存在理由：客户看交付物）——新增端点不许悄悄漏出这组
_MUST_INCLUDE = (
    "/api/v1/projects/{project_id}",
    "/api/v1/projects/{project_id}/documents",
    "/api/v1/projects/{project_id}/export",
)


def test_whitelist_properties():
    from src.main import app

    wl = viewer_whitelist(app)
    assert wl, "白名单为空——生成逻辑失效"
    assert all("{project_id}" in p for p in wl), "白名单必须全部是项目作用域端点"
    for p in _MUST_INCLUDE:
        assert p in wl, f"核心端点 {p} 未入白名单"


def test_whitelist_all_get_only():
    from src.main import app

    get_paths = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if "GET" in methods and "{project_id}" in path:
            get_paths.add(path)
    assert get_paths == set(viewer_whitelist(app)), "白名单必须精确等于项目作用域 GET 路径集"
    # 同路径可有写方法路由（如 POST documents）——白名单只承诺 GET 可达，写由 guard 矩阵拒绝
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if path in get_paths and "GET" not in methods:
            assert methods & {"POST", "PUT", "PATCH", "DELETE"}


def test_viewer_matrix_matches_whitelist(tmp_path):
    """行为级：client_viewer 对白名单路径 read 放行、write 403（guard 与白名单一致）。"""
    from fastapi.testclient import TestClient

    import src.auth as auth_mod
    from src.main import app

    provider = LocalAuthProvider(users_enabled=True, data_dir=str(tmp_path), admin_invite_code="A-1")
    reset_auth_provider()
    auth_mod._provider = provider
    try:
        # 块①boss：激活+邀请码（此后每块一个身份，防 cookie 覆盖踩坑）
        with TestClient(app) as c:
            r = c.post("/api/v1/auth/activate", json={"name": "boss", "password": "pass-12345", "invite_code": "A-1"})
            boss_id = r.json()["user_id"]
            invite = c.post("/api/v1/auth/invites").json()["invite_code"]
        # 块②guest：激活
        with TestClient(app) as c:
            r = c.post(
                "/api/v1/auth/activate", json={"name": "guest", "password": "guest-12345", "invite_code": invite}
            )
            guest_id = r.json()["user_id"]
        # 块③boss：建项目（boss 是 admin，创建即归属 boss；guest 无角色）+ 授 viewer
        with TestClient(app) as c:
            assert c.post("/api/v1/auth/login", json={"name": "boss", "password": "pass-12345"}).status_code == 200
            pid = c.post("/api/v1/projects", json={"name": "P"}).json()["project"]["id"]
            assert (
                c.put(f"/api/v1/auth/users/{guest_id}/projects/{pid}", json={"role": "client_viewer"}).status_code
                == 200
            )
        # 块④guest：矩阵验证（白名单路径 read 放行 / write 403）
        with TestClient(app) as c:
            assert c.post("/api/v1/auth/login", json={"name": "guest", "password": "guest-12345"}).status_code == 200
            assert c.get(f"/api/v1/projects/{pid}").status_code == 200  # read（白名单内端点）
            assert c.get(f"/api/v1/projects/{pid}/documents").status_code == 200
            assert c.post(f"/api/v1/projects/{pid}/documents", json={"title": "x"}).status_code == 403  # write 拒
        assert (
            provider.verify_project_access(
                type("U", (), {"is_admin": False, "project_roles": {pid: "client_viewer"}})(), pid, "write"
            )
            is False
        )
        assert boss_id  # noqa: S101 —— 仅为可读性锚点
    finally:
        reset_auth_provider()
