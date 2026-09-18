"""client_viewer 只读白名单（CE v0.5 二阶段，设计 25 号 §3.3）。

白名单由 OpenAPI 端点清单**自动生成**（非手写）：项目作用域（路径含 {project_id}）的 GET 端点全集。
与 LocalAuthProvider.verify_project_access 的 client_viewer 分支（action==read 才放行）保持一致：
- 白名单内的 GET：viewer 可访问（guard 判 read）
- 同路径的写方法（POST/PUT/PATCH/DELETE）：guard 判 write → 403
契约测试守护生成逻辑的性质（tests/contract/test_viewer_whitelist.py），防止未来新端点悄悄漏判。
"""

from __future__ import annotations


def viewer_whitelist(app) -> list[str]:
    """client_viewer 可访问端点清单（项目作用域 GET 集，排序稳定供快照测试）。"""
    out: list[str] = []
    for route in app.routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if "GET" in methods and "{project_id}" in path:
            out.append(path)
    return sorted(out)
