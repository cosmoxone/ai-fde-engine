#!/usr/bin/env python3
"""演示数据种子（demo/README.md 设计原则：幂等/走API/双形态/可重放）。

用法：
  python3 demo/seed.py --mode ce --base http://localhost:8000   # CE 本地多用户栈
  python3 demo/seed.py --mode te --base http://localhost:8014   # TE SaaS 栈（CASDoor@17100）
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
import urllib.error
import urllib.request
import uuid

PROJECT = "智驱制造-设备预测性维护（演示）"
DOCS = [
    ("现状调研", "客户现有维护体系以事后维修为主，关键设备停机损失每小时约 12 万元。痛点：备件库存高企但缺件频发；维修经验依赖老师傅，交接断层。目标：预测性维护覆盖 80% 关键设备。"),
    ("方案要点", "方案以振动与温度传感数据为基础，构建设备健康评分模型；分三期：试点（3 台关键机床）、扩展（全车间）、推广（全厂）。验收指标：误报率低于 5%，提前预警不低于 72 小时。"),
    ("经验沉淀", "行业经验：制造业预测性维护项目，数据质量比模型更重要——先做 4 周数据体检再建模；客户运维团队早期参与可将验收周期缩短约三分之一。"),
]


class Client:
    def __init__(self, base):
        self.base = base
        self.token = ""
        self.cookie = ""

    def _headers(self, auth=True):
        h = {"Content-Type": "application/json"}
        if auth and self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def call(self, method, path, body=None, auth=True):
        req = urllib.request.Request(self.base + path,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers=self._headers(auth), method=method)
        try:
            r = urllib.request.urlopen(req, timeout=25)
            return r.status, json.load(r), r.headers.get("Set-Cookie", "")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.load(e), ""
            except Exception:
                return e.code, {}, ""

    def upload_md(self, path, filename, text):
        """multipart 上传 .md（CE 契约：UploadFile；id 服务端生成）。"""
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"{filename}\"\r\nContent-Type: text/markdown\r\n\r\n{text}\r\n"
                f"--{boundary}--\r\n").encode()
        req = urllib.request.Request(self.base + path, data=body, method="POST", headers={
            **self._headers(), "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            r = urllib.request.urlopen(req, timeout=30)
            return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.load(e)
            except Exception:
                return e.code, {}


def _login_local(c: Client, creds) -> bool:
    for name, pw, invite in creds:
        s, d, ck = c.call("POST", "/api/v1/auth/login", {"name": name, "password": pw})
        if s == 200:
            c.cookie = (ck or "").split(";")[0] or c.cookie
            return True
        s, d, ck = c.call("POST", "/api/v1/auth/activate", {"name": name, "password": pw, "invite_code": invite})
        if s == 200:
            s, d, ck = c.call("POST", "/api/v1/auth/login", {"name": name, "password": pw})
            c.cookie = (ck or "").split(";")[0] or c.cookie
            return True
    return False


def seed_ce(base: str) -> None:
    c = Client(base)
    ok = _login_local(c, [("demo-admin", "demo-pass-123", "CE-DEPLOY-TEST-2026"),
                          ("boss", "deploy-pass-1", "CE-DEPLOY-TEST-2026")])
    assert ok, "admin 就位失败（栈已被第三方 admin 占用且无已知口令）"
    print("✓ admin 会话就位")
    _seed_common(c)


def seed_te(base: str, casdoor: str) -> None:
    if not casdoor:  # local/test 形态：走本地多用户认证（与 CE 同路）
        c = Client(base)
        ok = _login_local(c, [("demo-admin", "demo-pass-123",
                               os.environ.get("ADMIN_INVITE_CODE", "CE-DEPLOY-TEST-2026"))])
        assert ok, "TE local 形态 admin 就位失败（检查 ADMIN_INVITE_CODE）"
        print("✓ admin 会话就位（local 认证）")
        _seed_common(c)
        return
    cid = _env_file("ee/deploy/te-saas/.env", "CASDOOR_CLIENT_ID")
    cs = _env_file("ee/deploy/te-saas/.env", "CASDOOR_CLIENT_SECRET")
    req = urllib.request.Request(f"{casdoor}/api/login/oauth/access_token?grant_type=client_credentials",
                                 method="POST")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{cid}:{cs}".encode()).decode())
    tok = json.load(urllib.request.urlopen(req, timeout=15)).get("id_token", "")
    assert tok, "client_credentials 换 token 失败"
    c = Client(base)
    c.token = tok
    _seed_common(c)


def _env_file(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.strip().split("=", 1)[1]
    raise SystemExit(f"{key} 未在 {path} 找到")


def _seed_common(c: Client) -> None:
    s, d, _ = c.call("GET", "/api/v1/projects")
    pid = next((p["id"] for p in (d.get("projects") or []) if p.get("name") == PROJECT), None)
    if pid:
        print(f"✓ 演示项目已存在（幂等跳过建项）：{PROJECT}")
    else:
        s, d, _ = c.call("POST", "/api/v1/projects", {"name": PROJECT, "client_name": "智驱制造", "industry": "制造业"})
        assert s == 200, f"建项目失败: {d}"
        pid = d["project"]["id"]
        print(f"✓ 演示项目：{PROJECT}（{pid[:8]}…）")
    # 文档：multipart 上传（幂等=按文件名查重）
    s, d, _ = c.call("GET", f"/api/v1/projects/{pid}/documents")
    existing = {x.get("filename") for x in (d.get("documents") or [])}
    for title, text in DOCS:
        fn = f"{title}（演示）.md"
        if fn in existing:
            print(f"  ✓ 文档已存在（跳过）：{fn}")
            continue
        s, d = c.upload_md(f"/api/v1/projects/{pid}/documents", fn, f"# {title}\n\n{text}")
        print(f"  {'✓' if s in (200, 201) else '⚠'} 文档上传：{fn}" + ("" if s in (200, 201) else f"（{s} {str(d)[:50]}）"))
    # M3：发布（取服务端 doc id）+ 经验贡献（pending 演示审核队列）——CE 形态无 te 路由（运营面=TE 特性），探测即跳过
    s, d, _ = c.call("GET", "/api/te/kb/status")
    if s == 404:
        print("ℹ CE 形态：共享域/贡献队列属 TE 特性（/api/te/*）——跳过")
        return
    s, d, _ = c.call("GET", f"/api/v1/projects/{pid}/documents")
    doc_ids = [x["id"] for x in (d.get("documents") or [])]
    s, d, _ = c.call("POST", f"/api/te/projects/{pid}/kb/publish", {"doc_ids": doc_ids})
    print("✓ 共享域发布：" + (f"{len(d.get('publish', {}).get('docs', []))} 篇" if s == 200 else f"({s}) {str(d)[:60]}"))
    s, d, _ = c.call("GET", "/api/te/contributions")
    if not (d.get("contributions") or []):
        s, d, _ = c.call("POST", "/api/te/contributions",
                         {"kind": "memory", "payload": {"content": "制造业预测性维护：先做 4 周数据体检再建模；运维团队早期参与可缩短验收周期约三分之一。（演示贡献，待审核）"}})
        print("✓ 经验贡献入队（pending，演示审核流）：" + (str(d.get("contribution_id", "")) if s == 200 else f"({s})"))
    else:
        print("✓ 贡献队列已有数据（跳过）")
    s, d, _ = c.call("GET", "/api/te/kb/status")
    print("✓ 共享域状态：" + (f"mode={d.get('mode')} publications={d.get('shared_publications')}" if s == 200 else f"({s})"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ce", "te"], required=True)
    ap.add_argument("--base", default=None)
    ap.add_argument("--casdoor", default=None, help="CASDoor 地址（缺省=local 认证形态）")
    a = ap.parse_args()
    if a.mode == "ce":
        seed_ce(a.base or "http://localhost:8000")
    else:
        seed_te(a.base or "http://localhost:8014", a.casdoor)
    print(f"\n演示数据完成——Dashboard: {(a.base or '')}/dashboard")


if __name__ == "__main__":
    main()
