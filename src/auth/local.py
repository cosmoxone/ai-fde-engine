"""LocalAuthProvider——CE 默认认证实现（设计 25 号 v1.1 §3）。

两档（同 provider 内配置切换）：
- 单用户档（默认）：内置 local-admin，无登录页无用户表——v0.4 行为零变化
- 本地多用户档：LOCAL_USERS_ENABLED=true 时启用——独立 auth.db（local_users/project_members 两表）、
  邀请码激活流、本地口令（bcrypt 缺省 pbkdf2 替代）、签名 cookie 会话

刻意简单：面向 ≤10 人内网自托管小团队；无 OAuth/MFA/找回邮件——需要这些的团队即 TE 目标客户。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from .provider import User

# ---- 口令哈希（无外部依赖：PBKDF2-HMAC-SHA256，600k 轮） ----
_PBKDF2_ITER = 600_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITER).hex()
    return f"pbkdf2${_PBKDF2_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$", 3)
    except ValueError:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
    return hmac.compare_digest(calc, digest)


# ---- 签名 cookie 会话（itsdangerous-free：HMAC） ----
_SESSION_TTL = 7 * 24 * 3600


class _SessionCodec:
    def __init__(self, secret: str):
        self._secret = secret.encode()

    def issue(self, user_id: str) -> str:
        payload = f"{user_id}|{int(time.time()) + _SESSION_TTL}"
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}|{sig}"

    def parse(self, token: str) -> str | None:
        try:
            user_id, exp, sig = token.rsplit("|", 2)
            payload = f"{user_id}|{exp}"
            expect = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expect):
                return None
            if int(exp) < time.time():
                return None
            return user_id
        except (ValueError, TypeError):
            return None


class LocalAuthProvider:
    """本地认证（单用户/本地多用户两档）。"""

    NAME = "local"
    COOKIE = "aifde_session"

    def __init__(self, *, users_enabled: bool, data_dir: str, admin_invite_code: str = ""):
        self.users_enabled = users_enabled
        self._admin_invite = (admin_invite_code or "").strip()
        self._single = User(id="local-admin", display_name="本地管理员", platform_role="admin")
        self._router: APIRouter | None = None
        if users_enabled:
            db = Path(data_dir) / "auth.db"
            db.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS local_users(
                  id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                  pass_hash TEXT NOT NULL, platform_role TEXT NOT NULL DEFAULT 'member',
                  status TEXT NOT NULL DEFAULT 'active', created_at TEXT DEFAULT (datetime('now')));
                CREATE TABLE IF NOT EXISTS project_members(
                  project_id TEXT NOT NULL, user_id TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'fde',
                  PRIMARY KEY(project_id, user_id));
                """
            )
            self._conn.commit()
            secret_file = Path(data_dir) / "auth_session_secret"
            if secret_file.exists():
                self._secret = secret_file.read_text().strip()
            else:
                self._secret = secrets.token_hex(32)
                secret_file.write_text(self._secret)
                try:
                    os.chmod(secret_file, 0o600)
                except OSError:
                    pass
        else:
            self._conn = None
            self._secret = ""

        self._codec = _SessionCodec(self._secret or "single-user-mode")

    # ---- AuthProvider 协议实现 ----
    def current_user(self, request: Request) -> User:
        if not self.users_enabled:
            return self._single  # 单用户档：恒通过（v0.4 行为）
        token = request.cookies.get(self.COOKIE, "")
        user_id = self._codec.parse(token) if token else None
        if not user_id:
            raise HTTPException(status_code=401, detail="未登录")
        row = self._conn.execute("SELECT * FROM local_users WHERE id=? AND status='active'", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="用户不存在或已禁用")
        roles = {
            r["project_id"]: r["role"]
            for r in self._conn.execute("SELECT project_id, role FROM project_members WHERE user_id=?", (user_id,))
        }
        return User(id=row["id"], display_name=row["name"], platform_role=row["platform_role"], project_roles=roles)

    def verify_project_access(self, user: User, project_id: str, action: str = "read") -> bool:
        if not self.users_enabled or user.is_admin:
            return True
        role = user.project_roles.get(project_id)
        if role in ("project_owner", "fde"):
            return True
        if role == "domain_expert":
            return action in ("read", "review")
        if role == "client_viewer":
            return action == "read"
        return False  # 非成员不可见

    def login_routes(self) -> APIRouter:
        """固定路由结构（模块导入时挂载一次）；端点内部运行时取当前 provider——
        单例可被测试/替换（TE casdoor）而不失配。单用户档各端点返回明确提示。"""
        if self._router is not None:
            return self._router
        r = APIRouter(prefix="/api/v1/auth", tags=["auth"])

        def _active() -> "LocalAuthProvider":
            from . import get_auth_provider

            p = get_auth_provider()
            return p if isinstance(p, LocalAuthProvider) else self

        @r.get("/login")
        def login_page():
            p = _active()
            if not p.users_enabled:
                return HTMLResponse("<h3>单用户模式无需登录</h3>", status_code=200)
            admin_pending = p._admin_needs_activation()
            return HTMLResponse(_LOGIN_HTML.replace("__ADMIN_PENDING__", "true" if admin_pending else "false"))

        @r.post("/activate")
        async def activate(request: Request):
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse

            p = _active()
            if not p.users_enabled:
                raise HTTPException(403, "单用户模式无需激活（LOCAL_USERS_ENABLED=true 开启本地多用户）")
            body = await request.json()
            name = (body.get("name") or "").strip()
            password = body.get("password") or ""
            code = (body.get("invite_code") or "").strip()
            if not name or len(password) < 8:
                raise HTTPException(400, "用户名必填；口令至少 8 位")
            if p._admin_needs_activation():
                if not p._admin_invite or not secrets.compare_digest(code, p._admin_invite):
                    raise HTTPException(403, "管理员激活码不正确")
                role = "admin"
            else:
                if not p._valid_invite(code):
                    raise HTTPException(403, "邀请码无效或已使用")
                role = "member"
            uid = f"u-{secrets.token_hex(6)}"
            try:
                p._conn.execute(
                    "INSERT INTO local_users(id,name,pass_hash,platform_role) VALUES(?,?,?,?)",
                    (uid, name, hash_password(password), role),
                )
                p._conn.execute("DELETE FROM invite_codes WHERE code=?", (code,))
                p._conn.commit()
            except sqlite3.IntegrityError:
                raise HTTPException(409, "用户名已存在") from None
            out = JSONResponse({"success": True, "user_id": uid, "platform_role": role})
            out.set_cookie(p.COOKIE, p._codec.issue(uid), httponly=True, samesite="lax")
            return out

        @r.post("/login")
        async def login(request: Request):
            from fastapi import HTTPException
            from fastapi.responses import JSONResponse

            p = _active()
            if not p.users_enabled:
                raise HTTPException(403, "单用户模式无需登录")
            body = await request.json()
            name, password = (body.get("name") or "").strip(), body.get("password") or ""
            row = p._conn.execute("SELECT * FROM local_users WHERE name=? AND status='active'", (name,)).fetchone()
            if not row or not verify_password(password, row["pass_hash"]):
                raise HTTPException(401, "用户名或口令错误")
            out = JSONResponse({"success": True, "user_id": row["id"], "platform_role": row["platform_role"]})
            out.set_cookie(p.COOKIE, p._codec.issue(row["id"]), httponly=True, samesite="lax")
            return out

        @r.post("/logout")
        def logout():
            from fastapi.responses import JSONResponse

            p = _active()
            out = JSONResponse({"success": True})
            out.delete_cookie(p.COOKIE)
            return out

        @r.get("/me")
        def me(request: Request):
            p = _active()
            u = p.current_user(request)
            return {
                "success": True,
                "user": {
                    "id": u.id,
                    "display_name": u.display_name,
                    "platform_role": u.platform_role,
                    "project_roles": u.project_roles,
                },
                "users_enabled": p.users_enabled,
            }

        @r.post("/invites")
        def create_invite(request: Request):
            from fastapi import HTTPException

            p = _active()
            u = p.current_user(request)
            if not u.is_admin:
                raise HTTPException(403, "仅管理员可生成邀请码")
            code = secrets.token_hex(8)
            p._conn.execute("INSERT INTO invite_codes(code) VALUES(?)", (code,))
            p._conn.commit()
            return {"success": True, "invite_code": code}

        # ---- 成员管理（二阶段：admin 专用，29 号 §10 移交任务） ----
        @r.get("/users")
        def list_users(request: Request):
            p = _active()
            u = p.current_user(request)
            if not u.is_admin:
                raise HTTPException(403, "仅管理员可查看用户列表")
            return {"success": True, "users": p.list_users()}

        @r.patch("/users/{user_id}")
        async def update_user(user_id: str, request: Request):
            p = _active()
            u = p.current_user(request)
            if not u.is_admin:
                raise HTTPException(403, "仅管理员可修改用户")
            body = await request.json()
            status = body.get("status")
            role = body.get("platform_role")
            if status is not None and status not in ("active", "disabled"):
                raise HTTPException(400, "status 仅 active|disabled")
            if role is not None and role not in ("admin", "member"):
                raise HTTPException(400, "platform_role 仅 admin|member")
            # 保护：变更后不得无可用 admin（禁用自己/降级最后一个 admin 都会锁死系统）
            if user_id == u.id and (status == "disabled" or role == "member"):
                raise HTTPException(403, "不能禁用/降级当前登录的管理员")
            p.update_user(user_id, status=status, platform_role=role)
            return {"success": True}

        @r.put("/users/{user_id}/projects/{project_id}")
        async def assign_project_role(user_id: str, project_id: str, request: Request):
            p = _active()
            u = p.current_user(request)
            if not u.is_admin:
                raise HTTPException(403, "仅管理员可分配项目角色")
            body = await request.json()
            role = body.get("role", "")
            if role not in ("project_owner", "fde", "domain_expert", "client_viewer"):
                raise HTTPException(400, "role 仅 project_owner|fde|domain_expert|client_viewer")
            if not p._conn.execute("SELECT 1 FROM local_users WHERE id=?", (user_id,)).fetchone():
                raise HTTPException(404, "用户不存在")
            p.assign_member(project_id, user_id, role)
            return {"success": True}

        @r.delete("/users/{user_id}/projects/{project_id}")
        def remove_project_role(user_id: str, project_id: str, request: Request):
            p = _active()
            u = p.current_user(request)
            if not u.is_admin:
                raise HTTPException(403, "仅管理员可移除项目成员")
            p.remove_member(project_id, user_id)
            return {"success": True}

        self._router = r
        return r

    # ---- 用户/成员数据操作（供 API 层调用；单用户档调用为 no-op 防御） ----
    def list_users(self) -> list[dict]:
        if not self.users_enabled:
            return []
        rows = self._conn.execute(
            "SELECT id,name,platform_role,status,created_at FROM local_users ORDER BY created_at"
        ).fetchall()
        out = []
        for r in rows:
            roles = {
                m["project_id"]: m["role"]
                for m in self._conn.execute("SELECT project_id, role FROM project_members WHERE user_id=?", (r["id"],))
            }
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "platform_role": r["platform_role"],
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "project_roles": roles,
                }
            )
        return out

    def update_user(self, user_id: str, *, status: str | None = None, platform_role: str | None = None) -> bool:
        if not self.users_enabled:
            return False
        if status is not None:
            self._conn.execute("UPDATE local_users SET status=? WHERE id=?", (status, user_id))
        if platform_role is not None:
            self._conn.execute("UPDATE local_users SET platform_role=? WHERE id=?", (platform_role, user_id))
        self._conn.commit()
        return True

    def assign_member(self, project_id: str, user_id: str, role: str) -> None:
        if not self.users_enabled:
            return
        self._conn.execute(
            "INSERT INTO project_members(project_id,user_id,role) VALUES(?,?,?) "
            "ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role",
            (project_id, user_id, role),
        )
        self._conn.commit()

    def remove_member(self, project_id: str, user_id: str) -> None:
        if not self.users_enabled:
            return
        self._conn.execute("DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id))
        self._conn.commit()

    # ---- 内部 ----
    def _ensure_invite_table(self) -> None:
        self._conn.executescript(
            "CREATE TABLE IF NOT EXISTS invite_codes(code TEXT PRIMARY KEY, created_at TEXT DEFAULT (datetime('now')));"
        )
        self._conn.commit()

    def _admin_needs_activation(self) -> bool:
        self._ensure_invite_table()
        return self._conn.execute("SELECT COUNT(*) c FROM local_users WHERE platform_role='admin'").fetchone()["c"] == 0

    def _valid_invite(self, code: str) -> bool:
        self._ensure_invite_table()
        return bool(code and self._conn.execute("SELECT 1 FROM invite_codes WHERE code=?", (code,)).fetchone())


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>AI-FDE Engine 登录</title>
<style>
body{font-family:system-ui;background:#0d0f15;color:#e0e0e0;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
.card{background:#141726;border:1px solid #252836;border-radius:12px;padding:32px;width:360px}
h2{margin:0 0 8px;font-size:18px}.sub{color:#888;font-size:12px;margin-bottom:20px}
input{width:100%;padding:10px;margin-bottom:12px;background:#0f1117;border:1px solid #252836;border-radius:6px;color:#e0e0e0;box-sizing:border-box}
button{width:100%;padding:10px;background:#6c8cff;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}
.note{font-size:11px;color:#666;margin-top:14px}
</style></head><body><div class="card">
<h2>AI-FDE Engine</h2><div class="sub">本地多用户模式</div>
<input id="name" placeholder="用户名">
<input id="password" type="password" placeholder="口令（≥8 位）">
<input id="code" placeholder="__ADMIN_PENDING__">
<button onclick="go()">登录 / 激活</button>
<div class="note">首次使用：管理员用激活码注册；之后用口令登录。</div>
</div><script>
const ADMIN_PENDING = __ADMIN_PENDING__;
document.getElementById('code').placeholder = ADMIN_PENDING ? '管理员激活码' : '邀请码（新用户）/ 留空登录';
async function go(){
  const b={name:v('name'),password:v('password'),invite_code:v('code')};
  let r=await fetch('/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
  if((r.status===401||r.status===403) && b.invite_code){ r=await fetch('/api/v1/auth/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});}
  const j=await r.json();
  if(r.ok){location.href='/dashboard';}else{alert(j.detail||'失败');}
}
function v(id){return document.getElementById(id).value;}
</script></body></html>"""
