#!/usr/bin/env python3
"""
AI-FDE Engine MCP Server - Model Context Protocol 服务端
让AI工具（Claude Desktop、Cursor、Cline、Windsurf等）可以直接调用AI-FDE Engine的核心功能

工具列表：
  - health_check          健康检查
  - create_project        创建项目
  - list_projects         列出项目
  - get_project           获取项目详情
  - run_research          触发调研分析（异步）
  - run_design            触发方案设计（异步）
  - run_delivery          触开发交付（异步）
  - get_task_status       查询任务状态
  - list_reviews          列出待审核项
  - approve_review        审核通过
  - reject_review         审核驳回
  - get_ss_progress       获取自助交付进度
  - identify_opportunities AI落地机会识别
  - get_value_dashboard   获取价值仪表盘

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

    def request(self, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{self.base_url}/api/v1{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if requests:
            try:
                resp = requests.request(method, url, json=data, headers=headers, timeout=30)
                return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            import urllib.request
            import urllib.error
            req_data = json.dumps(data).encode() if data else None
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
        return client.request("POST", "/projects", {
            "name": args["name"],
            "client_name": args.get("client_name", ""),
            "industry": args.get("industry", ""),
            "description": args.get("description", ""),
        })

    elif name == "list_projects":
        return client.request("GET", "/projects")

    elif name == "get_project":
        return client.request("GET", f"/projects/{args['project_id']}")

    elif name == "run_research":
        return client.request("POST", f"/projects/{args['project_id']}/research/run", {
            "client_requirements": args.get("client_requirements", ""),
            "interview_notes": args.get("interview_notes", ""),
        })

    elif name == "run_design":
        return client.request("POST", f"/projects/{args['project_id']}/design/run", {
            "requirements_baseline": args.get("requirements_baseline"),
        })

    elif name == "run_delivery":
        return client.request("POST", f"/projects/{args['project_id']}/delivery/run", {
            "task_type": args.get("task_type", "generate_code"),
            "badcases": [],
        })

    elif name == "get_task_status":
        return client.request("GET", f"/tasks/{args['task_id']}")

    elif name == "list_reviews":
        return client.request("GET", "/self-service/review/pending")

    elif name == "approve_review":
        return client.request("POST", f"/self-service/review/{args['review_id']}/action", {
            "action": "approve",
            "comment": args.get("comment", ""),
            "reviewer": args.get("reviewer", ""),
        })

    elif name == "reject_review":
        return client.request("POST", f"/self-service/review/{args['review_id']}/action", {
            "action": "reject",
            "comment": args.get("comment", ""),
            "reviewer": args.get("reviewer", ""),
        })

    elif name == "get_ss_progress":
        return client.request("GET", f"/projects/{args['project_id']}/self-service/progress")

    elif name == "identify_opportunities":
        return client.request("POST", f"/projects/{args['project_id']}/self-service/opportunities", {
            "business_description": args["business_description"],
            "industry": args.get("industry", ""),
            "pain_points": [],
        })

    elif name == "get_value_dashboard":
        return client.request("GET", f"/projects/{args['project_id']}/self-service/value")

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
