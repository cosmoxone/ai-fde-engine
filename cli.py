#!/usr/bin/env python3
"""
AI-FDE Engine CLI - 命令行接口
前后端分离架构：CLI通过HTTP API调用后端服务，可独立部署使用
也可被其他工具（脚本、CI/CD、自动化工作流）直接调用

用法：
  aifde project list                    # 列出项目
  aifde project create --name "测试"    # 创建项目
  aifde agent research --project-id XXX  # 触发调研分析
  aifde task show --task-id XXX         # 查看任务状态
  aifde review list                      # 查看待审核队列
  aifde review approve --review-id XXX   # 审核通过
  aifde self-service progress --project-id XXX  # 查看自助交付进度
  aifde dashboard                        # 打开Dashboard控制台
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import webbrowser
from typing import Any, Optional

try:
    import requests
except ImportError:
    requests = None  # 允许无requests时使用urllib


class AIFDEClient:
    """AI-FDE Engine API客户端"""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base_url = (base_url or os.environ.get("AIFDE_API_URL", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or os.environ.get("AIFDE_API_KEY", "")
        self._session = None

    def _get_session(self):
        if self._session is None:
            if requests:
                self._session = requests.Session()
                if self.api_key:
                    self._session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            else:
                self._session = "urllib"
        return self._session

    def request(self, method: str, path: str, data: Optional[dict] = None, timeout: int = 30) -> dict:
        """发送API请求"""
        url = f"{self.base_url}/api/v1{path}"
        session = self._get_session()

        if session == "urllib":
            import urllib.request
            import urllib.error
            req_data = json.dumps(data).encode() if data else None
            req = urllib.request.Request(url, data=req_data, method=method.upper())
            req.add_header("Content-Type", "application/json")
            if self.api_key:
                req.add_header("Authorization", f"Bearer {self.api_key}")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            try:
                resp = session.request(method.upper(), url, json=data, timeout=timeout)
                return resp.json()
            except Exception as e:
                return {"success": False, "error": str(e)}

    def health_check(self) -> dict:
        url = f"{self.base_url}/api/v1/health"
        if requests:
            return requests.get(url, timeout=5).json()
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())


# ===== 输出格式化 =====

def print_table(headers: list[str], rows: list[list[Any]], max_col_width: int = 40):
    """打印格式化表格"""
    if not rows:
        print("  (无数据)")
        return
    # 计算列宽
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = min(max(col_widths[i], len(str(cell))), max_col_width)
    # 打印表头
    header_line = "  " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("  " + "-+-".join("-" * w for w in col_widths))
    # 打印数据行
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            s = str(cell) if cell is not None else "-"
            if len(s) > max_col_width:
                s = s[:max_col_width - 3] + "..."
            cells.append(s.ljust(col_widths[i]) if i < len(col_widths) else s)
        print("  " + " | ".join(cells))


def print_json(data: Any, indent: int = 2):
    """打印JSON"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


def status_badge(status: str) -> str:
    """状态标签"""
    colors = {
        "running": "\033[94m", "completed": "\033[92m", "failed": "\033[91m",
        "pending": "\033[93m", "approved": "\033[92m", "rejected": "\033[91m",
    }
    reset = "\033[0m"
    color = colors.get(status, "\033[90m")
    return f"{color}{status}{reset}"


# ===== CLI命令实现 =====

def cmd_health(args, client: AIFDEClient):
    """健康检查"""
    try:
        result = client.health_check()
        status = result.get("status", "unknown")
        print(f"  服务状态: {status_badge(status)}")
        print(f"  服务地址: {client.base_url}")
        if "version" in result:
            print(f"  版本: {result.get('version')}")
    except Exception as e:
        print(f"  \033[91m连接失败: {e}\033[0m")
        print(f"  请确认服务已启动: {client.base_url}")
        sys.exit(1)


def cmd_project_list(args, client: AIFDEClient):
    """列出项目"""
    result = client.request("GET", "/projects")
    projects = result.get("projects", [])
    print(f"\n  项目总数: {len(projects)}\n")
    rows = [[
        p.get("id", "")[:12],
        p.get("name", ""),
        p.get("client_name", "-"),
        p.get("industry", "-"),
        p.get("status", "-"),
        f"{p.get('progress', 0)}%",
    ] for p in projects]
    print_table(["ID", "名称", "客户", "行业", "状态", "进度"], rows)
    print()


def cmd_project_create(args, client: AIFDEClient):
    """创建项目"""
    data = {"name": args.name}
    if args.client:
        data["client_name"] = args.client
    if args.industry:
        data["industry"] = args.industry
    if args.description:
        data["description"] = args.description
    result = client.request("POST", "/projects", data)
    if result.get("success"):
        proj = result.get("project", {})
        print(f"\n  \033[92m✓ 项目创建成功\033[0m")
        print(f"  ID: {proj.get('id')}")
        print(f"  名称: {proj.get('name')}")
        print(f"  状态: {proj.get('status')}")
        print(f"\n  下一步: aifde agent research --project-id {proj.get('id')}")
    else:
        print(f"  \033[91m✗ 创建失败: {result.get('error')}\033[0m")
        sys.exit(1)
    print()


def cmd_project_show(args, client: AIFDEClient):
    """查看项目详情"""
    result = client.request("GET", f"/projects/{args.project_id}")
    if not result.get("success") and "project" not in result:
        print(f"  \033[91m项目不存在\033[0m")
        sys.exit(1)
    proj = result.get("project", result)
    print(f"\n  项目详情: {proj.get('name')}")
    print(f"  {'='*50}")
    print(f"  ID: {proj.get('id')}")
    print(f"  客户: {proj.get('client_name', '-')}")
    print(f"  行业: {proj.get('industry', '-')}")
    print(f"  状态: {status_badge(proj.get('status', '-'))}")
    print(f"  进度: {proj.get('progress', 0)}%")
    if args.verbose:
        print(f"\n  完整数据:")
        print_json(proj)
    print()


def cmd_agent_run(args, client: AIFDEClient):
    """触发Agent任务"""
    agent_type = args.agent_type
    path_map = {
        "research": "/research/run",
        "design": "/design/run",
        "delivery": "/delivery/run",
        "benchmark": "/benchmarks/generate",
        "iteration": "/iteration/run",
    }
    if agent_type not in path_map:
        print(f"  \033[91m未知Agent类型: {agent_type}\033[0m")
        print(f"  可选: {', '.join(path_map.keys())}")
        sys.exit(1)

    data = {}
    if agent_type == "delivery":
        data["task_type"] = args.task_type or "generate_code"
        data["badcases"] = []
    if agent_type == "iteration":
        data["badcases"] = []

    result = client.request("POST", f"/projects/{args.project_id}{path_map[agent_type]}", data)
    if result.get("success"):
        task_id = result.get("task_id")
        print(f"\n  \033[94m⚡ {agent_type}任务已启动\033[0m")
        print(f"  任务ID: {task_id}")
        print(f"  项目ID: {args.project_id}")
        print(f"\n  查看状态: aifde task show --task-id {task_id}")
        if args.watch:
            print(f"\n  等待完成...")
            _watch_task(client, task_id)
    else:
        print(f"  \033[91m✗ 启动失败: {result.get('error')}\033[0m")
        sys.exit(1)
    print()


def _watch_task(client: AIFDEClient, task_id: str, interval: int = 3, timeout: int = 300):
    """轮询等待任务完成"""
    start = time.time()
    while time.time() - start < timeout:
        result = client.request("GET", f"/tasks/{task_id}")
        task = result.get("task", result)
        status = task.get("status", "unknown")
        elapsed = time.time() - start
        print(f"  [{elapsed:.0f}s] 状态: {status_badge(status)}")
        if status in ("completed", "failed"):
            if status == "completed":
                print(f"\n  \033[92m✓ 任务完成\033[0m")
                if "result" in task:
                    print(f"  结果摘要: {json.dumps(task['result'], ensure_ascii=False)[:200]}...")
            else:
                print(f"\n  \033[91m✗ 任务失败: {task.get('error')}\033[0m")
            return
        time.sleep(interval)
    print(f"  \033[93m超时（{timeout}s），任务仍在运行\033[0m")


def cmd_task_list(args, client: AIFDEClient):
    """列出任务（需要指定项目）"""
    if not args.project_id:
        print("  \033[93m提示: 使用 --project-id 指定项目查看任务列表\033[0m")
        return
    result = client.request("GET", f"/projects/{args.project_id}/tasks")
    tasks = result.get("tasks", [])
    print(f"\n  项目任务数: {len(tasks)}\n")
    rows = [[
        t.get("id", t.get("task_id", ""))[:12],
        t.get("type", "-"),
        t.get("status", "-"),
        f"{t.get('duration_seconds', 0):.1f}s" if t.get("duration_seconds") else "-",
    ] for t in tasks]
    print_table(["任务ID", "类型", "状态", "耗时"], rows)
    print()


def cmd_task_show(args, client: AIFDEClient):
    """查看任务详情"""
    result = client.request("GET", f"/tasks/{args.task_id}")
    task = result.get("task", result)
    print(f"\n  任务详情")
    print(f"  {'='*50}")
    print(f"  任务ID: {task.get('id', task.get('task_id'))}")
    print(f"  类型: {task.get('type', '-')}")
    print(f"  状态: {status_badge(task.get('status', '-'))}")
    if "duration_seconds" in task:
        print(f"  耗时: {task['duration_seconds']:.2f}s")
    if "error" in task:
        print(f"  错误: \033[91m{task['error']}\033[0m")
    if "result" in task and args.verbose:
        print(f"\n  执行结果:")
        print_json(task["result"])
    print()


def cmd_review_list(args, client: AIFDEClient):
    """查看审核队列"""
    result = client.request("GET", "/self-service/review/pending")
    reviews = result.get("reviews", [])
    print(f"\n  待审核: {result.get('pending_count', len(reviews))} 项\n")
    if not reviews:
        print("  (暂无待审核项)")
    else:
        rows = [[
            r.get("review_id", "")[:12],
            r.get("type", "-"),
            r.get("project_id", "")[:12],
            r.get("status", "-"),
            time.strftime("%m-%d %H:%M", time.localtime(r.get("created_at", 0))),
        ] for r in reviews]
        print_table(["审核ID", "类型", "项目", "状态", "创建时间"], rows)
    print()


def cmd_review_action(args, client: AIFDEClient):
    """审核操作"""
    action = "approve" if args.approve else "reject"
    data = {"action": action, "comment": args.comment or ""}
    if args.reviewer:
        data["reviewer"] = args.reviewer
    result = client.request("POST", f"/self-service/review/{args.review_id}/action", data)
    if result.get("success"):
        review = result.get("review", {})
        print(f"\n  \033[92m✓ 审核完成\033[0m")
        print(f"  审核ID: {review.get('review_id')}")
        print(f"  操作: {status_badge(review.get('status'))}")
        if review.get("comment"):
            print(f"  批注: {review.get('comment')}")
    else:
        print(f"  \033[91m✗ 操作失败: {result.get('error')}\033[0m")
        sys.exit(1)
    print()


def cmd_selfservice_progress(args, client: AIFDEClient):
    """查看自助交付进度"""
    result = client.request("GET", f"/projects/{args.project_id}/self-service/progress")
    if not result.get("success"):
        print(f"  \033[91m获取失败: {result.get('error')}\033[0m")
        sys.exit(1)
    prog = result["progress"]
    print(f"\n  自助交付进度: {prog['progress_percentage']:.0f}%")
    print(f"  当前阶段: {prog.get('current_step_name', '已完成')}")
    print(f"  已完成: {prog['completed_steps']}/{prog['total_steps']}\n")
    for step in prog["steps"]:
        marker = "✓" if step["completed"] else ("→" if step["step_id"] == prog["current_step"] else " ")
        print(f"  [{marker}] {step['order']}. {step['step_name']}")
    print()


def cmd_selfservice_opportunities(args, client: AIFDEClient):
    """AI落地机会识别"""
    data = {"business_description": args.description, "industry": args.industry or ""}
    result = client.request("POST", f"/projects/{args.project_id}/self-service/opportunities", data)
    if result.get("success"):
        print(f"\n  \033[94m⚡ 机会识别任务已启动\033[0m")
        print(f"  任务ID: {result.get('task_id')}")
        if args.watch:
            _watch_task(client, result["task_id"])
    else:
        print(f"  \033[91m✗ 失败: {result.get('error')}\033[0m")
    print()


def cmd_selfservice_value(args, client: AIFDEClient):
    """查看价值仪表盘"""
    result = client.request("GET", f"/projects/{args.project_id}/self-service/value")
    if result.get("success"):
        value = result.get("value", {})
        metrics = value.get("metrics", [])
        print(f"\n  价值仪表盘\n")
        if metrics:
            rows = [[
                m.get("name", ""),
                m.get("category", ""),
                f"{m.get('current_value', '-')}",
                f"{m.get('target_value', '-')}",
                m.get("unit", ""),
                f"\033[92m+{m.get('improvement_percentage', 0):.1f}%\033[0m",
            ] for m in metrics]
            print_table(["指标", "维度", "当前值", "目标值", "单位", "提升"], rows)
        if "summary" in value:
            print(f"\n  平均提升: {value['summary'].get('average_improvement', 0):.1f}%")
    else:
        print(f"  \033[91m获取失败\033[0m")
    print()


def cmd_dashboard(args, client: AIFDEClient):
    """打开Dashboard"""
    url = f"{client.base_url}/dashboard"
    print(f"  Dashboard地址: {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
            print("  已在浏览器中打开")
        except Exception:
            print("  请手动在浏览器中打开上述地址")
    print()


# ===== 主入口 =====

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aifde",
        description="AI-FDE Engine CLI - AI驱动的FDE交付引擎命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  aifde health
  aifde project list
  aifde project create --name "智能客服项目" --industry 电商
  aifde agent research --project-id XXX --watch
  aifde agent delivery --project-id XXX --task-type generate_code
  aifde task show --task-id XXX
  aifde review list
  aifde review approve --review-id XXX --comment "通过"
  aifde self-service progress --project-id XXX
  aifde dashboard

环境变量:
  AIFDE_API_URL    API服务地址 (默认: http://localhost:8000)
  AIFDE_API_KEY    API密钥 (可选)
        """,
    )
    parser.add_argument("--url", default=None, help="API服务地址")
    parser.add_argument("--api-key", default=None, help="API密钥")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # health
    subparsers.add_parser("health", help="健康检查")

    # project
    proj_parser = subparsers.add_parser("project", help="项目管理")
    proj_sub = proj_parser.add_subparsers(dest="project_command")
    proj_sub.add_parser("list", help="列出项目")
    create_p = proj_sub.add_parser("create", help="创建项目")
    create_p.add_argument("--name", required=True, help="项目名称")
    create_p.add_argument("--client", help="客户名称")
    create_p.add_argument("--industry", help="行业")
    create_p.add_argument("--description", help="项目描述")
    show_p = proj_sub.add_parser("show", help="查看项目详情")
    show_p.add_argument("--project-id", required=True, help="项目ID")
    show_p.add_argument("-v", "--verbose", action="store_true", help="显示完整数据")

    # agent
    agent_p = subparsers.add_parser("agent", help="触发Agent任务")
    agent_p.add_argument("agent_type", choices=["research", "design", "delivery", "benchmark", "iteration"], help="Agent类型")
    agent_p.add_argument("--project-id", required=True, help="项目ID")
    agent_p.add_argument("--task-type", default=None, help="交付任务类型 (delivery专用)")
    agent_p.add_argument("--watch", action="store_true", help="等待任务完成")

    # task
    task_p = subparsers.add_parser("task", help="任务管理")
    task_sub = task_p.add_subparsers(dest="task_command")
    list_t = task_sub.add_parser("list", help="列出项目任务")
    list_t.add_argument("--project-id", help="项目ID")
    show_t = task_sub.add_parser("show", help="查看任务详情")
    show_t.add_argument("--task-id", required=True, help="任务ID")
    show_t.add_argument("-v", "--verbose", action="store_true", help="显示完整结果")

    # review
    review_p = subparsers.add_parser("review", help="审核工作台")
    review_sub = review_p.add_subparsers(dest="review_command")
    review_sub.add_parser("list", help="待审核列表")
    approve_p = review_sub.add_parser("approve", help="审核通过")
    approve_p.add_argument("--review-id", required=True, help="审核ID")
    approve_p.add_argument("--comment", help="批注")
    approve_p.add_argument("--reviewer", help="审核人")
    reject_p = review_sub.add_parser("reject", help="审核驳回")
    reject_p.add_argument("--review-id", required=True, help="审核ID")
    reject_p.add_argument("--comment", help="驳回原因")
    reject_p.add_argument("--reviewer", help="审核人")

    # self-service
    ss_p = subparsers.add_parser("self-service", help="自助交付")
    ss_sub = ss_p.add_subparsers(dest="ss_command")
    prog_p = ss_sub.add_parser("progress", help="查看进度")
    prog_p.add_argument("--project-id", required=True, help="项目ID")
    opp_p = ss_sub.add_parser("opportunities", help="AI落地机会识别")
    opp_p.add_argument("--project-id", required=True, help="项目ID")
    opp_p.add_argument("--description", required=True, help="业务描述")
    opp_p.add_argument("--industry", help="行业")
    opp_p.add_argument("--watch", action="store_true", help="等待完成")
    val_p = ss_sub.add_parser("value", help="价值仪表盘")
    val_p.add_argument("--project-id", required=True, help="项目ID")

    # dashboard
    dash_p = subparsers.add_parser("dashboard", help="打开Dashboard控制台")
    dash_p.add_argument("--no-browser", action="store_true", help="不打开浏览器，仅显示地址")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    client = AIFDEClient(base_url=args.url, api_key=args.api_key)

    try:
        if args.command == "health":
            cmd_health(args, client)
        elif args.command == "project":
            if args.project_command == "list":
                cmd_project_list(args, client)
            elif args.project_command == "create":
                cmd_project_create(args, client)
            elif args.project_command == "show":
                cmd_project_show(args, client)
            else:
                parser.parse_args(["project", "--help"])
        elif args.command == "agent":
            cmd_agent_run(args, client)
        elif args.command == "task":
            if args.task_command == "list":
                cmd_task_list(args, client)
            elif args.task_command == "show":
                cmd_task_show(args, client)
            else:
                parser.parse_args(["task", "--help"])
        elif args.command == "review":
            if args.review_command == "list":
                cmd_review_list(args, client)
            elif args.review_command == "approve":
                args.approve = True
                cmd_review_action(args, client)
            elif args.review_command == "reject":
                args.approve = False
                cmd_review_action(args, client)
            else:
                parser.parse_args(["review", "--help"])
        elif args.command == "self-service":
            if args.ss_command == "progress":
                cmd_selfservice_progress(args, client)
            elif args.ss_command == "opportunities":
                cmd_selfservice_opportunities(args, client)
            elif args.ss_command == "value":
                cmd_selfservice_value(args, client)
            else:
                parser.parse_args(["self-service", "--help"])
        elif args.command == "dashboard":
            cmd_dashboard(args, client)
        else:
            parser.print_help()
    except KeyboardInterrupt:
        print("\n  已取消")
        sys.exit(130)
    except Exception as e:
        print(f"\n  \033[91m错误: {e}\033[0m")
        sys.exit(1)


if __name__ == "__main__":
    main()
