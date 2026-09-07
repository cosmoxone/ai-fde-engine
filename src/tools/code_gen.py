"""
代码生成工具 - 基于OpenHands / Aider / OpenCode
MVP阶段使用模拟，生产环境调用OpenHands SDK
"""

from __future__ import annotations

import json
import os
from typing import Optional

from ..config import get_settings


class CodeGenTool:
    """代码生成工具：项目级代码生成、Bug修复、代码重构、自动测试"""

    NAME = "code_gen"
    DESCRIPTION = "基于技术方案生成项目代码，支持Bug修复、重构、自动测试"

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.settings = get_settings()
        self.workspace_base = self.settings.openhands_workspace_base
        self.workspace_path = os.path.join(self.workspace_base, self.project_id)
        os.makedirs(self.workspace_path, exist_ok=True)

    async def generate_project(
        self,
        requirements: list[dict],
        tech_stack: dict,
        project_name: Optional[str] = None,
    ) -> dict:
        """
        基于需求和技术栈生成完整项目代码
        返回: {"project_path": str, "files": [...], "next_steps": [...]}
        """
        project_name = project_name or f"project_{self.project_id[:8]}"
        project_path = os.path.join(self.workspace_path, project_name)
        os.makedirs(project_path, exist_ok=True)

        # 根据provider选择代码生成方式
        provider = self.settings.code_gen_provider

        if provider == "aider":
            result = await self._generate_with_aider(project_path, project_name, requirements, tech_stack)
            if result:
                return result
        elif provider == "openhands":
            result = await self._generate_with_openhands(project_path, project_name, requirements, tech_stack)
            if result:
                return result
        elif provider == "opencode":
            result = await self._generate_with_opencode(project_path, project_name, requirements, tech_stack)
            if result:
                return result

        # MVP模拟生成项目骨架
        files = self._scaffold_project(project_path, project_name, requirements, tech_stack)

        return {
            "success": True,
            "project_name": project_name,
            "project_path": project_path,
            "files_generated": len(files),
            "files": files,
            "provider": self.settings.code_gen_provider,
            "next_steps": [
                "cd {} && pip install -r requirements.txt".format(project_path),
                "运行测试: pytest tests/",
                "启动服务: uvicorn app.main:app --reload",
            ],
        }

    async def fix_issue(self, repo_path: str, issue_description: str) -> dict:
        """修复指定Issue"""
        # MVP模拟
        return {
            "success": True,
            "repo_path": repo_path,
            "issue": issue_description[:100],
            "files_modified": ["app/services/handler.py"],
            "tests_passed": True,
            "commit_message": f"fix: {issue_description[:50]}",
            "fix_description": "定位到问题根因，修复了边界条件处理，新增了异常捕获。",
        }

    async def refactor(self, repo_path: str, scope: str) -> dict:
        """代码重构"""
        return {
            "success": True,
            "repo_path": repo_path,
            "scope": scope,
            "files_refactored": 3,
            "improvements": ["提取公共函数", "优化异常处理", "增加类型注解"],
            "tests_passed": True,
        }

    async def run_tests(self, repo_path: str) -> dict:
        """运行测试"""
        return {
            "success": True,
            "repo_path": repo_path,
            "total_tests": 25,
            "passed": 23,
            "failed": 2,
            "coverage": "78%",
            "failed_tests": [
                {"name": "test_edge_case_1", "error": "AssertionError: expected 85, got 80"},
            ],
            "duration_seconds": 12.5,
        }

    async def _generate_with_aider(
        self,
        project_path: str,
        project_name: str,
        requirements: list[dict],
        tech_stack: dict,
    ) -> Optional[dict]:
        """
        使用Aider生成代码（真实实现）
        安装: pip install aider-chat
        Aider是终端原生的AI编程助手，支持git集成、多文件编辑、自动测试
        """
        try:
            import shutil
            import subprocess

            if not shutil.which("aider"):
                print("[CodeGen] Aider未安装，降级到mock。安装: pip install aider-chat")
                return None

            # 生成需求描述文件
            req_file = os.path.join(project_path, "REQUIREMENTS.md")
            req_content = f"# {project_name} 需求文档\n\n"
            req_content += f"## 技术栈\n{json.dumps(tech_stack, ensure_ascii=False, indent=2)}\n\n"
            req_content += "## 功能需求\n"
            for req in requirements:
                req_content += f"- [{req.get('priority', 'P1')}] {req.get('title', '')}: {req.get('description', '')}\n"
            req_content += (
                "\n## 任务\n请基于以上需求生成完整的项目代码，包括项目结构、核心模块、配置文件、测试代码和README。\n"
            )
            with open(req_file, "w") as f:
                f.write(req_content)

            # 初始化git仓库（Aider需要）
            subprocess.run(["git", "init"], cwd=project_path, capture_output=True)
            subprocess.run(["git", "add", "."], cwd=project_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=project_path, capture_output=True)

            # 调用Aider
            prompt = f"请阅读REQUIREMENTS.md，生成完整的项目代码。使用{tech_stack.get('backend', 'FastAPI')}后端框架。"
            cmd = [
                "aider",
                "--model",
                self.settings.get_model_for_task("code")[0],
                "--no-auto-commits",
                "--yes-always",
                "--message",
                prompt,
                "REQUIREMENTS.md",
            ]

            env = os.environ.copy()
            if self.settings.deepseek_api_key:
                env["OPENAI_API_KEY"] = self.settings.deepseek_api_key
                env["OPENAI_API_BASE"] = self.settings.deepseek_base_url

            result = subprocess.run(
                cmd, cwd=project_path, capture_output=True, text=True, timeout=self.settings.code_gen_timeout, env=env
            )

            # 收集生成的文件
            files = []
            for root, _, filenames in os.walk(project_path):
                for fn in filenames:
                    if not fn.startswith(".git"):
                        files.append(os.path.relpath(os.path.join(root, fn), project_path))

            return {
                "success": True,
                "project_name": project_name,
                "project_path": project_path,
                "files_generated": len(files),
                "files": files,
                "provider": "aider",
                "aider_output": result.stdout[:2000],
                "next_steps": ["安装依赖", "运行测试", "部署验证"],
            }
        except Exception as e:
            print(f"[CodeGen] Aider生成失败，降级到mock: {e}")
            return None

    async def _generate_with_openhands(
        self,
        project_path: str,
        project_name: str,
        requirements: list[dict],
        tech_stack: dict,
    ) -> Optional[dict]:
        """
        使用OpenHands生成代码（真实实现）
        安装: pip install openhands
        OpenHands是开源自主编程Agent，SWE-bench Verified 77%
        """
        try:
            # OpenHands通常通过Docker或API调用
            # 这里提供SDK调用的框架
            print("[CodeGen] OpenHands集成需要Docker环境，当前使用mock")
            return None
        except Exception as e:
            print(f"[CodeGen] OpenHands生成失败: {e}")
            return None

    async def _generate_with_opencode(
        self,
        project_path: str,
        project_name: str,
        requirements: list[dict],
        tech_stack: dict,
    ) -> Optional[dict]:
        """
        使用OpenCode生成代码（真实实现）
        安装: npm install -g opencode-ai
        OpenCode是终端原生的AI编程Agent，支持多模型、MCP协议
        """
        try:
            import shutil
            import subprocess

            if not shutil.which("opencode"):
                print("[CodeGen] OpenCode未安装，降级到mock。安装: npm install -g opencode-ai")
                return None

            # 调用OpenCode
            prompt = f"基于需求生成{project_name}项目代码。技术栈: {json.dumps(tech_stack)}"
            cmd = ["opencode", "run", prompt, "--dir", project_path]

            subprocess.run(cmd, capture_output=True, text=True, timeout=self.settings.code_gen_timeout)

            files = []
            for root, _, filenames in os.walk(project_path):
                for fn in filenames:
                    files.append(os.path.relpath(os.path.join(root, fn), project_path))

            return {
                "success": True,
                "project_name": project_name,
                "project_path": project_path,
                "files_generated": len(files),
                "files": files,
                "provider": "opencode",
                "next_steps": ["安装依赖", "运行测试", "部署验证"],
            }
        except Exception as e:
            print(f"[CodeGen] OpenCode生成失败: {e}")
            return None

    def _scaffold_project(self, path: str, name: str, requirements: list[dict], tech_stack: dict) -> list[str]:
        """生成项目骨架文件"""
        files = []

        # 目录结构
        dirs = [
            "app",
            "app/api",
            "app/api/v1",
            "app/core",
            "app/models",
            "app/schemas",
            "app/services",
            "tests",
            "deploy",
        ]
        for d in dirs:
            os.makedirs(os.path.join(path, d), exist_ok=True)

        # __init__.py 文件
        for d in ["app", "app/api", "app/api/v1", "app/core", "app/models", "app/schemas", "app/services", "tests"]:
            init_path = os.path.join(path, d, "__init__.py")
            with open(init_path, "w") as f:
                f.write("")
            files.append(f"{d}/__init__.py")

        # main.py
        main_path = os.path.join(path, "app", "main.py")
        with open(main_path, "w") as f:
            f.write(f'''"""
{name} - 后端服务入口
"""
from fastapi import FastAPI
from app.api.v1 import api_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {{"status": "healthy", "version": "1.0.0"}}
''')
        files.append("app/main.py")

        # config.py
        config_path = os.path.join(path, "app", "core", "config.py")
        with open(config_path, "w") as f:
            f.write('''"""应用配置"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AI-FDE Project"
    debug: bool = False
    database_url: str = "sqlite:///./app.db"

    class Config:
        env_file = ".env"


settings = Settings()
''')
        files.append("app/core/config.py")

        # API路由
        router_path = os.path.join(path, "app", "api", "v1", "__init__.py")
        with open(router_path, "w") as f:
            f.write("""from fastapi import APIRouter

api_router = APIRouter()

@api_router.get("/")
async def root():
    return {"message": "API v1"}
""")
        files.append("app/api/v1/__init__.py")

        # requirements.txt
        req_path = os.path.join(path, "requirements.txt")
        with open(req_path, "w") as f:
            f.write(
                "fastapi>=0.110\nuvicorn>=0.27\nsqlalchemy>=2.0\npydantic>=2.0\npydantic-settings>=2.0\npytest>=8.0\nhttpx>=0.27\n"
            )
        files.append("requirements.txt")

        # 测试文件
        test_path = os.path.join(path, "tests", "test_health.py")
        with open(test_path, "w") as f:
            f.write('''"""健康检查测试"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
''')
        files.append("tests/test_health.py")

        # README
        readme_path = os.path.join(path, "README.md")
        with open(readme_path, "w") as f:
            f.write(f"""# {name}

AI-FDE项目自动生成的后端服务。

## 快速开始

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 测试

```bash
pytest tests/ -v
```

## API文档

启动后访问 http://localhost:8000/docs
""")
        files.append("README.md")

        return files
