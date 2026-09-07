"""
MCP Server 工具测试（v0.1.4 C2）

mcp 包未安装时通过 TOOLS 数据结构与 dispatch 覆盖性静态校验
（mcp_server.py 顶部 import mcp 依赖 mcp 包，测试用 AST 方式提取）。
"""

from __future__ import annotations

import ast
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MCP_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server.py")

# 提取 TOOLS 定义（不 import，避免依赖 mcp/requests 包）


def _load_tools_and_dispatch() -> tuple[list[dict], set[str]]:
    tree = ast.parse(open(MCP_FILE, encoding="utf-8").read())
    tools: list[dict] = []
    dispatch_names: set[str] = set()
    for node in ast.walk(tree):
        assigns = []
        if isinstance(node, ast.Assign):
            assigns = list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assigns = [node.target]
        for t in assigns:
            if isinstance(t, ast.Name) and t.id == "TOOLS":
                tools = ast.literal_eval(node.value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_dispatch":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Compare) and isinstance(sub.left, ast.Name) and sub.left.id == "name":
                    for comp in sub.comparators:
                        if isinstance(comp, ast.Constant):
                            dispatch_names.add(comp.value)
    return tools, dispatch_names


TOOLS, DISPATCH = _load_tools_and_dispatch()


class TestToolsCatalog:
    def test_26_tools(self):
        assert len(TOOLS) == 26

    def test_every_tool_has_schema_and_description(self):
        for t in TOOLS:
            assert t["name"], t
            assert t["description"]
            assert t["inputSchema"]["type"] == "object"
            assert isinstance(t["inputSchema"].get("properties", {}), dict)

    def test_unique_names(self):
        names = [t["name"] for t in TOOLS]
        assert len(names) == len(set(names))

    def test_full_delivery_flow_covered(self):
        """完整交付流程工具链齐备（C2 验收）"""
        names = {t["name"] for t in TOOLS}
        expected = {
            "create_project",
            "upload_document",
            "run_research",
            "run_design",
            "generate_benchmark",
            "run_benchmark_eval",
            "submit_badcase",
            "run_iteration",
            "export_list",
            "export_deliverables",
            "edit_requirement",
            "search_memory",
            "list_reviews",
            "approve_review",
        }
        missing = expected - names
        assert not missing, f"缺少工具: {missing}"


class TestDispatchCoverage:
    def test_every_tool_dispatched(self):
        tool_names = {t["name"] for t in TOOLS}
        missing = tool_names - DISPATCH
        assert not missing, f"TOOLS 定义但 _dispatch 未处理: {missing}"

    def test_dispatch_no_orphans(self):
        tool_names = {t["name"] for t in TOOLS}
        orphans = DISPATCH - tool_names - {"未知工具"}
        # dispatch 里 name == "未知工具" 的 else 分支字符串
        orphans = {o for o in orphans if o != "未知工具"}
        assert not orphans, f"_dispatch 分支无对应工具: {orphans}"


mcp_installed = True
try:
    import mcp  # noqa: F401
except ImportError:
    mcp_installed = False


@pytest.mark.skipif(not mcp_installed, reason="mcp 包未安装（可选依赖）")
class TestMCPRuntime:
    def test_server_importable_and_registered(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("mcp_server_under_test", MCP_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tools = mod.TOOLS
        assert len(tools) == 26
