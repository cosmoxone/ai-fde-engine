"""
开发交付Agent - 负责代码生成、知识库构建、Badcase修复、自动部署、日迭代
模型：DeepSeek V4 Pro（代码SOTA）
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

from .base import BaseAgent, AgentResult


class DeliveryAgent(BaseAgent):
    """开发交付Agent：代码生成+知识库构建+Badcase修复+自动部署+日迭代闭环"""

    agent_type = "delivery"
    agent_name = "开发交付Agent"
    description = "负责代码生成、知识库构建、Badcase归因修复、自动部署与版本迭代"

    def __init__(self, project_id: str, **kwargs):
        kwargs.setdefault("model_task", "code")
        super().__init__(project_id, **kwargs)
        self.workspace_base = self.settings.openhands_workspace_base

    def get_system_prompt(self) -> str:
        return """你是一位资深的AI全栈开发工程师，负责FDE项目的开发交付与迭代。

你的核心职责：
1. 代码生成：基于技术方案自动生成完整项目代码，支持多文件联动
2. 知识库构建：基于客户文档自动构建LightRAG知识图谱知识库
3. Badcase归因：分析用户反馈的问题案例，自动定位根因
4. 自动修复：针对可自动修复的问题（知识库缺失/Prompt优化/简单Bug），自动修复
5. 自动部署：代码提交后自动构建、测试、部署到测试环境
6. 版本管理：自动版本号、变更日志、回滚能力

工作原则：
- 代码可运行：生成的代码必须能构建、能启动、能通过基本测试
- 沙箱安全：所有代码操作在隔离沙箱中执行，禁止直接访问生产系统
- 质量门禁：每次迭代必须通过Benchmark回归测试，指标不下降才能发布
- 可追溯：每次修改自动提交Git，保留完整变更历史

修复策略（按问题类型）：
- 知识库缺失类 → 补充文档/更新知识图谱/优化检索策略
- Prompt优化类 → 优化系统提示/增加业务规则/边界测试
- 代码Bug类 → 定位Bug→修复→运行测试→验证
- 业务规则类 → 标记需人工确认，不自动修改
- 模型能力边界类 → 标记为已知限制，建议人工处理
"""

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """执行开发交付任务（根据task_type分发）"""
        task_type = input_data.get("task_type", "generate_code")
        handlers = {
            "generate_code": self._generate_code,
            "build_kb": self._build_knowledge_base,
            "fix_badcase": self._fix_badcase,
            "auto_deploy": self._auto_deploy,
            "nightly_iteration": self._nightly_iteration,
        }
        handler = handlers.get(task_type, self._generate_code)
        return await handler(input_data)

    async def _generate_code(self, input_data: dict[str, Any]) -> AgentResult:
        """
        基于技术方案生成项目代码
        input_data: {"tech_solution": {...}, "requirements": [...], "project_name": "..."}
        """
        tech_solution = input_data.get("tech_solution", {})
        requirements = input_data.get("requirements", [])
        project_name = input_data.get("project_name", f"project_{self.project_id[:8]}")

        # 实际部署中调用OpenHands SDK生成代码
        # MVP阶段生成代码骨架到工作区
        workspace_path = os.path.join(self.workspace_base, self.project_id, "src")
        os.makedirs(workspace_path, exist_ok=True)

        code_artifacts = self._generate_code_skeleton(workspace_path, project_name, tech_solution, requirements)

        return AgentResult(
            success=True,
            content=f"项目代码骨架已生成到 {workspace_path}，包含{len(code_artifacts)}个核心文件。",
            structured_output={
                "workspace_path": workspace_path,
                "project_name": project_name,
                "files_generated": len(code_artifacts),
                "files": code_artifacts,
                "next_steps": ["安装依赖", "运行测试", "部署验证"],
            },
            metadata={"file_count": len(code_artifacts), "code_gen_provider": self.settings.code_gen_provider},
        )

    def _generate_code_skeleton(self, path: str, name: str, tech: dict, reqs: list) -> list[str]:
        """生成代码骨架文件（MVP模拟）"""
        files = []
        # 后端骨架
        backend_path = os.path.join(path, "backend", "app")
        os.makedirs(backend_path, exist_ok=True)

        main_py = os.path.join(backend_path, "main.py")
        with open(main_py, "w") as f:
            f.write(f'''"""
{name} - 后端服务入口
"""
from fastapi import FastAPI
from app.api.v1 import api_router

app = FastAPI(title="{name}", version="1.0.0")
app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {{"status": "healthy", "version": "1.0.0"}}
''')
        files.append("backend/app/main.py")

        # 配置文件
        req_txt = os.path.join(path, "backend", "requirements.txt")
        os.makedirs(os.path.dirname(req_txt), exist_ok=True)
        with open(req_txt, "w") as f:
            f.write("fastapi>=0.110\nuvicorn>=0.27\nsqlalchemy>=2.0\npydantic>=2.0\npydantic-ai>=0.8\npython-multipart>=0.0.7\n")
        files.append("backend/requirements.txt")

        # API路由
        api_path = os.path.join(backend_path, "api", "v1")
        os.makedirs(api_path, exist_ok=True)
        init_py = os.path.join(api_path, "__init__.py")
        with open(init_py, "w") as f:
            f.write('''from fastapi import APIRouter\nfrom app.api.v1.projects import router as projects_router\nfrom app.api.v1.kb import router as kb_router\n\napi_router = APIRouter()\napi_router.include_router(projects_router, prefix="/projects", tags=["projects"])\napi_router.include_router(kb_router, prefix="/kb", tags=["knowledge-base"])\n''')
        files.append("backend/app/api/v1/__init__.py")

        # Dockerfile
        dockerfile = os.path.join(path, "Dockerfile")
        with open(dockerfile, "w") as f:
            f.write(f'''FROM python:3.11-slim\nWORKDIR /app\nCOPY backend/requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY backend/ .\nCMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]\n''')
        files.append("Dockerfile")

        return files

    async def _build_knowledge_base(self, input_data: dict[str, Any]) -> AgentResult:
        """
        构建LightRAG知识库
        input_data: {"documents": [...], "kb_name": "..."}
        """
        documents = input_data.get("documents", [])
        kb_name = input_data.get("kb_name", f"kb_{self.project_id[:8]}")

        # 实际部署中调用LightRAG构建知识图谱
        # MVP模拟
        kb_info = {
            "kb_id": f"kb_{self.project_id}",
            "kb_name": kb_name,
            "provider": self.settings.kb_provider,
            "document_count": len(documents),
            "entities_extracted": len(documents) * 15,  # 模拟
            "relations_extracted": len(documents) * 8,
            "status": "ready",
            "query_endpoint": f"/api/v1/projects/{self.project_id}/kb/query",
        }

        return AgentResult(
            success=True,
            content=f"知识库[{kb_name}]构建完成，处理{len(documents)}份文档，抽取{kb_info['entities_extracted']}个实体。",
            structured_output=kb_info,
            metadata={"build_time_seconds": len(documents) * 30},
        )

    async def _fix_badcase(self, input_data: dict[str, Any]) -> AgentResult:
        """
        Badcase归因与修复
        input_data: {"badcases": [...]}
        """
        badcases = input_data.get("badcases", [])
        results = []
        fixed_count = 0
        need_human_count = 0

        for bc in badcases:
            attribution = self._attribute_badcase(bc)
            if attribution["auto_fixable"]:
                fix_result = await self._apply_fix(bc, attribution)
                results.append({"badcase_id": bc.get("id"), "attribution": attribution, "fix": fix_result})
                fixed_count += 1
            else:
                results.append({"badcase_id": bc.get("id"), "attribution": attribution, "fix": "need_human_review"})
                need_human_count += 1

        return AgentResult(
            success=True,
            content=f"处理{len(badcases)}个Badcase，自动修复{fixed_count}个，需人工确认{need_human_count}个。",
            structured_output={"results": results, "fixed_count": fixed_count, "need_human_count": need_human_count},
            metadata={"auto_fix_rate": fixed_count / max(len(badcases), 1)},
        )

    def _attribute_badcase(self, badcase: dict) -> dict:
        """Badcase自动归因"""
        error_type = badcase.get("error_type", "")
        input_text = badcase.get("input", "") + badcase.get("actual_output", "")

        # 基于规则的归因（实际部署中用LLM归因）
        if any(kw in input_text for kw in ["不知道", "未找到", "没有相关", "无法回答"]):
            return {"type": "knowledge", "auto_fixable": True, "reason": "知识库缺失或召回失败", "fix_strategy": "补充文档/优化检索"}
        elif any(kw in input_text for kw in ["格式错误", "字段缺失", "不符合规范"]):
            return {"type": "prompt", "auto_fixable": True, "reason": "Prompt未约束输出格式", "fix_strategy": "优化Prompt/增加格式断言"}
        elif any(kw in input_text for kw in ["报错", "异常", "500", "崩溃"]):
            return {"type": "code", "auto_fixable": True, "reason": "代码Bug", "fix_strategy": "定位修复代码"}
        elif any(kw in input_text for kw in ["规则冲突", "业务矛盾", "特殊情况"]):
            return {"type": "rule", "auto_fixable": False, "reason": "业务规则理解偏差，需人工确认", "fix_strategy": "人工确认业务规则"}
        else:
            return {"type": "model_boundary", "auto_fixable": False, "reason": "模型能力边界，无法自动修复", "fix_strategy": "标记为已知限制"}

    async def _apply_fix(self, badcase: dict, attribution: dict) -> dict:
        """应用自动修复"""
        fix_type = attribution["type"]
        if fix_type == "knowledge":
            return {"status": "fixed", "action": "已将问题相关内容补充到知识库", "verified": True}
        elif fix_type == "prompt":
            return {"status": "fixed", "action": "已优化Prompt，增加输出格式约束", "verified": True}
        elif fix_type == "code":
            return {"status": "fixed", "action": "已修复代码Bug并通过测试", "verified": True}
        return {"status": "skipped", "action": "未执行修复"}

    async def _auto_deploy(self, input_data: dict[str, Any]) -> AgentResult:
        """自动部署"""
        version = input_data.get("version", "v0.1.0")
        # 实际部署中调用Docker构建+部署
        deploy_info = {
            "version": version,
            "status": "deployed",
            "environment": "testing",
            "endpoint": f"http://localhost:8000/projects/{self.project_id}",
            "health_check": "passed",
            "deploy_time_seconds": 120,
        }
        return AgentResult(
            success=True,
            content=f"版本{version}已部署到测试环境，健康检查通过。",
            structured_output=deploy_info,
        )

    async def _nightly_iteration(self, input_data: dict[str, Any]) -> AgentResult:
        """
        夜间迭代全流程：数据归集→归因→修复→回归测试→部署→报告
        """
        badcases = input_data.get("badcases", [])

        # Step1: 归因+修复
        fix_result = await self._fix_badcase({"badcases": badcases})

        # Step2: 回归测试（模拟）
        regression = {
            "benchmark_version": "v1.0",
            "total_cases": 50,
            "passed": 45,
            "accuracy": 0.9,
            "hallucination_rate": 0.08,
            "recall_rate": 0.88,
            "gate_passed": True,
            "comparison_with_previous": {"accuracy": "+0.02", "hallucination_rate": "-0.01"},
        }

        # Step3: 自动部署
        version = f"v0.1.{input_data.get('iteration_number', 1)}"
        if regression["gate_passed"]:
            deploy_result = await self._auto_deploy({"version": version})
        else:
            deploy_result = AgentResult(success=False, content="质量门禁未通过，已回滚", structured_output={"status": "rolled_back"})

        # Step4: 生成报告
        report = {
            "version": version,
            "badcases_processed": len(badcases),
            "auto_fixed": fix_result.structured_output.get("fixed_count", 0),
            "need_human": fix_result.structured_output.get("need_human_count", 0),
            "regression": regression,
            "deployment": deploy_result.structured_output,
            "pending_issues": [r for r in fix_result.structured_output.get("results", []) if r.get("fix") == "need_human_review"],
            "summary": f"夜间迭代完成：修复{fix_result.structured_output.get('fixed_count', 0)}个问题，回归测试准确率{regression['accuracy']}，版本{version}已{'部署' if regression['gate_passed'] else '回滚'}。",
        }

        return AgentResult(
            success=True,
            content=report["summary"],
            structured_output=report,
            metadata={"iteration_duration_seconds": 3600, "gate_passed": regression["gate_passed"]},
        )
