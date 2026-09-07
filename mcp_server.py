#!/usr/bin/env python3
"""
AI-FDE Engine MCP Server - Model Context Protocol 服务端
让AI工具（Claude Desktop、Cursor、Cline、Windsurf等）可以直接调用AI-FDE Engine的核心功能

工具列表（26个，覆盖完整交付流程）：
  项目:  health_check / create_project / list_projects / get_project
  文档:  upload_document / list_documents
  分析:  run_research / run_design / run_delivery / get_task_status
  质量:  generate_benchmark / list_benchmarks / run_benchmark_eval
        submit_badcase / list_badcases / run_iteration
  交付:  export_list / export_deliverables / edit_requirement
  审核:  list_reviews / approve_review / reject_review
  自助:  get_ss_progress / identify_opportunities / get_value_dashboard
  记忆:  search_memory

用法（Claude Desktop配置）：
  {
    "mcpServers": {
      "ai-fde": {
        "command": "python3",
        "args": ["/path/to/mcp_server.py"],
        "env": { "AIFDE_API_URL": "http://localhost:8000" }
      }
    }
  }
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

try:
    import requests
except ImportError:
    requests = None


class AIFDEMCPClient:
    """MCP Server内部使用的API客户端"""

    def __init__(self):
        self.base_url = os.environ.get("AIFDE_API_URL", "http://localhost:8000").rstrip("/")
        self.api_key = os.environ.get("AIFDE_API_KEY", "")

    def request(self, method: str, path: str, data: dict | None = None, files: dict | None = None) -> dict:
        url = f"{self.base_url}/api/v1{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if files:
            # multipart 上传（不设 Content-Type，由 requests/urllib 边界生成）
            headers.pop("Content-Type", None)

        if requests:
            try:
                resp = requests.request(method, url, json=data, headers=headers, timeout=30, files=files)
                return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            import urllib.error
            import urllib.request

            if files:
                # 手工构造 multipart（无 requests 依赖时的上传降级）
                import uuid as _uuid

                boundary = f"----aifde{_uuid.uuid4().hex}"
                body_parts = []
                for field_name, (fname, content, ftype) in files.items():
                    body_parts.append(
                        f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
                        f'filename="{fname}"\r\nContent-Type: {ftype}\r\n\r\n'.encode("utf-8")
                        + content
                        + b"\r\n"
                    )
                body_parts.append(f"--{boundary}--\r\n".encode())
                req_data = b"".join(body_parts)
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    method=method,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
            else:
                req_data = json.dumps(data).encode() if data is not None else None
                req = urllib.request.Request(url, data=req_data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                return {"success": False, "error": f"HTTP {e.code}"}
            except Exception as e:
                return {"success": False, "error": str(e)}


# 创建MCP Server实例
server = Server("ai-fde-engine")
client = AIFDEMCPClient()


# ===== 工具定义 =====

TOOLS: list[dict[str, Any]] = [
    {
        "name": "health_check",
        "description": "检查AI-FDE Engine服务是否正常运行",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "create_project",
        "description": "创建一个新的AI落地项目",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "项目名称"},
                "client_name": {"type": "string", "description": "客户名称"},
                "industry": {"type": "string", "description": "所属行业"},
                "description": {"type": "string", "description": "项目描述"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_projects",
        "description": "列出所有AI落地项目",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_project",
        "description": "获取指定项目的详细信息",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "run_research",
        "description": "触发调研分析Agent（异步任务，返回task_id用于查询状态）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "client_requirements": {"type": "string", "description": "客户需求描述"},
                "interview_notes": {"type": "string", "description": "访谈笔记"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "run_design",
        "description": "触发方案设计Agent（异步任务）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "requirements_baseline": {"type": "object", "description": "需求基线（可选，默认使用项目已有基线）"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "run_delivery",
        "description": "触开发交付Agent（异步任务，支持代码生成/Badcase修复/完整交付）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "task_type": {
                    "type": "string",
                    "description": "交付任务类型",
                    "enum": ["generate_code", "fix_badcase", "full_delivery", "deploy"],
                    "default": "generate_code",
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_task_status",
        "description": "查询异步任务的执行状态和结果",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "任务ID"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "list_reviews",
        "description": "列出待人工审核的任务结果（后台异步完成后自动入队）",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "approve_review",
        "description": "审核通过某个待审核项",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_id": {"type": "string", "description": "审核项ID"},
                "comment": {"type": "string", "description": "审核批注"},
                "reviewer": {"type": "string", "description": "审核人"},
            },
            "required": ["review_id"],
        },
    },
    {
        "name": "reject_review",
        "description": "审核驳回某个待审核项",
        "inputSchema": {
            "type": "object",
            "properties": {
                "review_id": {"type": "string", "description": "审核项ID"},
                "comment": {"type": "string", "description": "驳回原因"},
                "reviewer": {"type": "string", "description": "审核人"},
            },
            "required": ["review_id", "comment"],
        },
    },
    {
        "name": "get_ss_progress",
        "description": "获取自助交付项目的引导进度（5步流程）",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "identify_opportunities",
        "description": "AI落地机会识别：基于业务描述识别高ROI的AI应用场景",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "business_description": {"type": "string", "description": "业务描述"},
                "industry": {"type": "string", "description": "行业"},
            },
            "required": ["project_id", "business_description"],
        },
    },
    {
        "name": "get_value_dashboard",
        "description": "获取项目的价值仪表盘（效率/成本/质量/满意度四维指标+ROI）",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "upload_document",
        "description": "上传业务文档内容到项目（文本直传，用于调研分析输入）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "filename": {"type": "string", "description": "文件名，如 质检手册.md"},
                "content": {"type": "string", "description": "文档文本内容"},
            },
            "required": ["project_id", "filename", "content"],
        },
    },
    {
        "name": "list_documents",
        "description": "列出项目已上传的文档",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "generate_benchmark",
        "description": "基于项目文档生成Benchmark测试集（50条：高频/边界/对抗），无文档时用行业模板种子",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "list_benchmarks",
        "description": "列出项目Benchmark测试集",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "run_benchmark_eval",
        "description": "对Benchmark执行评测（准确率/幻觉率/召回率+质量门禁判定）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "benchmark_id": {"type": "string", "description": "Benchmark ID"},
            },
            "required": ["project_id", "benchmark_id"],
        },
    },
    {
        "name": "run_iteration",
        "description": "触发夜间迭代：自动归集badcase→归因修复/生成建议→回归→质量门禁→部署",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "badcases": {"type": "array", "description": "坏例列表（可选，默认自动归集open状态）"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "submit_badcase",
        "description": "提交一条Badcase（坏例）反馈，供夜间迭代处理",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "input": {"type": "string", "description": "用户输入"},
                "actual_output": {"type": "string", "description": "实际错误输出"},
                "expected_output": {"type": "string", "description": "期望输出"},
                "error_type": {"type": "string", "description": "knowledge/prompt/rule/model_boundary"},
            },
            "required": ["project_id", "input", "actual_output", "expected_output"],
        },
    },
    {
        "name": "list_badcases",
        "description": "列出项目Badcase（可按状态过滤 open/processed）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "status": {"type": "string", "description": "状态过滤"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "export_deliverables",
        "description": "导出交付物单项内容（markdown）：01-项目概览/02-需求基线/03-方案设计/04-Benchmark测试集/05-迭代报告/06-评审记录；先调用 export_list 查看可选项",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "item": {"type": "string", "description": "交付物key，如 02-需求基线"},
            },
            "required": ["project_id", "item"],
        },
    },
    {
        "name": "export_list",
        "description": "列出项目可导出的交付物清单",
        "inputSchema": {
            "type": "object",
            "properties": {"project_id": {"type": "string", "description": "项目ID"}},
            "required": ["project_id"],
        },
    },
    {
        "name": "edit_requirement",
        "description": "编辑需求基线中的单个需求项（人工修订AI产出，修改进入基线并可导出）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "req_id": {"type": "string", "description": "需求ID，如 R1"},
                "title": {"type": "string", "description": "标题"},
                "description": {"type": "string", "description": "描述"},
                "priority": {"type": "string", "description": "P0/P1/P2"},
                "acceptance_criteria": {"type": "string", "description": "量化验收标准"},
            },
            "required": ["project_id", "req_id"],
        },
    },
    {
        "name": "search_memory",
        "description": "检索项目跨会话记忆（历史经验/决策/教训）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "项目ID"},
                "query": {"type": "string", "description": "检索关键词"},
                "limit": {"type": "integer", "description": "返回条数"},
            },
            "required": ["project_id", "query"],
        },
    },
]


# ===== MCP Server 处理器 =====


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出所有可用工具"""
    return [
        Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """执行工具调用"""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))]


async def _dispatch(name: str, args: dict[str, Any]) -> dict:
    """工具分发"""
    if name == "health_check":
        try:
            import urllib.request

            with urllib.request.urlopen(f"{client.base_url}/api/v1/health", timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"success": False, "error": f"服务不可用: {e}", "api_url": client.base_url}

    elif name == "create_project":
        return client.request(
            "POST",
            "/projects",
            {
                "name": args["name"],
                "client_name": args.get("client_name", ""),
                "industry": args.get("industry", ""),
                "description": args.get("description", ""),
            },
        )

    elif name == "list_projects":
        return client.request("GET", "/projects")

    elif name == "get_project":
        return client.request("GET", f"/projects/{args['project_id']}")

    elif name == "run_research":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/research/run",
            {
                "client_requirements": args.get("client_requirements", ""),
                "interview_notes": args.get("interview_notes", ""),
            },
        )

    elif name == "run_design":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/design/run",
            {
                "requirements_baseline": args.get("requirements_baseline"),
            },
        )

    elif name == "run_delivery":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/delivery/run",
            {
                "task_type": args.get("task_type", "generate_code"),
                "badcases": [],
            },
        )

    elif name == "get_task_status":
        return client.request("GET", f"/tasks/{args['task_id']}")

    elif name == "list_reviews":
        return client.request("GET", "/self-service/review/pending")

    elif name == "approve_review":
        return client.request(
            "POST",
            f"/self-service/review/{args['review_id']}/action",
            {
                "action": "approve",
                "comment": args.get("comment", ""),
                "reviewer": args.get("reviewer", ""),
            },
        )

    elif name == "reject_review":
        return client.request(
            "POST",
            f"/self-service/review/{args['review_id']}/action",
            {
                "action": "reject",
                "comment": args.get("comment", ""),
                "reviewer": args.get("reviewer", ""),
            },
        )

    elif name == "get_ss_progress":
        return client.request("GET", f"/projects/{args['project_id']}/self-service/progress")

    elif name == "identify_opportunities":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/self-service/opportunities",
            {
                "business_description": args["business_description"],
                "industry": args.get("industry", ""),
                "pain_points": [],
            },
        )

    elif name == "get_value_dashboard":
        return client.request("GET", f"/projects/{args['project_id']}/self-service/value")

    elif name == "upload_document":
        # multipart 上传（requests files 参数）
        pid = args["project_id"]
        return client.request(
            "POST",
            f"/projects/{pid}/documents",
            data=None,
            files={"file": (args["filename"], args["content"].encode("utf-8"), "text/markdown")},
        )

    elif name == "list_documents":
        return client.request("GET", f"/projects/{args['project_id']}/documents")

    elif name == "generate_benchmark":
        return client.request("POST", f"/projects/{args['project_id']}/benchmarks/generate", {})

    elif name == "list_benchmarks":
        return client.request("GET", f"/projects/{args['project_id']}/benchmarks")

    elif name == "run_benchmark_eval":
        return client.request("POST", f"/projects/{args['project_id']}/benchmarks/{args['benchmark_id']}/evaluate", {})

    elif name == "run_iteration":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/iteration/run",
            {"badcases": args.get("badcases") or [], "benchmark_cases": []},
        )

    elif name == "submit_badcase":
        return client.request(
            "POST",
            f"/projects/{args['project_id']}/badcases",
            {
                "input": args["input"],
                "actual_output": args["actual_output"],
                "expected_output": args["expected_output"],
                "error_type": args.get("error_type", "knowledge"),
                "severity": "medium",
            },
        )

    elif name == "list_badcases":
        path = f"/projects/{args['project_id']}/badcases"
        if args.get("status"):
            path += f"?status={args['status']}"
        return client.request("GET", path)

    elif name == "export_list":
        return client.request("GET", f"/projects/{args['project_id']}/export/list")

    elif name == "export_deliverables":
        # MCP 场景返回单项 markdown 文本（zip 不适合模型消费）
        from urllib.parse import quote

        item = quote(args["item"])
        return client.request("GET", f"/projects/{args['project_id']}/export?format=md&item={item}")

    elif name == "edit_requirement":
        body = {k: args[k] for k in ("title", "description", "priority", "acceptance_criteria") if k in args}
        return client.request("PATCH", f"/projects/{args['project_id']}/requirements/{args['req_id']}", body)

    elif name == "search_memory":
        return client.request(
            "GET",
            f"/projects/{args['project_id']}/memory/search?query={args['query']}&limit={args.get('limit', 10)}",
        )

    else:
        return {"success": False, "error": f"未知工具: {name}"}


# ===== 主入口 =====


async def main():
    """启动MCP Server（stdio传输）"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
