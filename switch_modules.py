#!/usr/bin/env python3
"""
AI-FDE Engine 模块自动化切换脚本
====================================
按照模块切换指南，自动化完成从Mock到真实模块的切换、验证和回滚。

用法:
  python switch_modules.py status              # 查看当前各模块状态
  python switch_modules.py check               # 检测环境就绪情况
  python switch_modules.py run --module llm    # 切换指定模块
  python switch_modules.py run --all           # 一键全量切换（按优先级顺序）
  python switch_modules.py run --all --parallel # 并行切换无依赖模块（加速）
  python switch_modules.py rollback --module llm # 回滚指定模块
  python switch_modules.py rollback --all      # 全量回滚到mock
  python switch_modules.py verify --module llm # 验证指定模块
  python switch_modules.py report              # 生成切换报告

选项:
  --dry-run          只检测不执行
  --auto-install     自动安装缺失的pip依赖
  --skip-verify      切换后跳过验证（加速）
  --env-file PATH    指定.env文件路径（默认deploy/.env）
  --verbose          详细输出
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
ENV_FILE_DEFAULT = PROJECT_ROOT / "deploy" / ".env"
ENV_EXAMPLE = PROJECT_ROOT / "deploy" / ".env.example"
BACKUP_DIR = PROJECT_ROOT / ".switch_backups"

# 确保项目模块可导入
sys.path.insert(0, str(PROJECT_ROOT))


# ============================================
# 模块定义
# ============================================

@dataclass
class ModuleDef:
    """模块定义"""
    name: str
    display_name: str
    priority: int  # 1=最高，数字越小越先切换
    provider_config_key: str  # .env中的配置项名
    mock_value: str
    real_values: list[str]  # 可选的真实provider值
    default_real_value: str
    pip_dependencies: list[str]
    env_keys_required: list[str]  # 必须配置的环境变量（API Key等）
    services_required: list[str]  # 需要的外部服务（docker服务名）
    description: str
    depends_on: list[str] = field(default_factory=list)  # 依赖的其他模块
    parallel_group: str = ""  # 同组模块可并行切换


MODULES: dict[str, ModuleDef] = {
    "llm": ModuleDef(
        name="llm",
        display_name="LLM大模型层",
        priority=1,
        provider_config_key="LLM_PROVIDER",
        mock_value="mock",
        real_values=["deepseek", "qwen", "openai", "ollama"],
        default_real_value="deepseek",
        pip_dependencies=[],  # 纯HTTP API，无需额外依赖
        env_keys_required=["DEEPSEEK_API_KEY", "QWEN_API_KEY"],  # 至少一个
        services_required=[],
        description="DeepSeek V4 / Qwen3.6 真实API调用，所有Agent的基础",
        parallel_group="core",
    ),
    "doc_parser": ModuleDef(
        name="doc_parser",
        display_name="文档解析层",
        priority=2,
        provider_config_key="DOC_PARSER_PROVIDER",
        mock_value="mock",
        real_values=["docling", "marker", "hybrid"],
        default_real_value="docling",
        pip_dependencies=["docling"],
        env_keys_required=[],
        services_required=[],
        description="Docling多格式文档解析 / Marker v2 GPU加速PDF解析",
        depends_on=["llm"],  # 文档解析后的结构化可能需要LLM
        parallel_group="data",
    ),
    "knowledge_base": ModuleDef(
        name="knowledge_base",
        display_name="知识库层",
        priority=2,
        provider_config_key="KB_PROVIDER",
        mock_value="mock",
        real_values=["qdrant", "lightrag", "basic"],
        default_real_value="qdrant",
        pip_dependencies=["qdrant-client", "sentence-transformers"],
        env_keys_required=[],
        services_required=["qdrant"],
        description="Qdrant向量数据库 + bge-m3 Embedding + 知识图谱检索",
        depends_on=["llm"],
        parallel_group="data",
    ),
    "evaluation": ModuleDef(
        name="evaluation",
        display_name="评测引擎层",
        priority=3,
        provider_config_key="EVALUATION_PROVIDER",
        mock_value="mock",
        real_values=["deepeval"],
        default_real_value="deepeval",
        pip_dependencies=["deepeval"],
        env_keys_required=["DEEPSEEK_API_KEY", "QWEN_API_KEY"],  # LLM-as-judge需要
        services_required=[],
        description="DeepEval 50+评测指标（幻觉/相关性/忠实度/毒性/偏见）",
        depends_on=["llm"],
        parallel_group="quality",
    ),
    "code_gen": ModuleDef(
        name="code_gen",
        display_name="代码生成层",
        priority=4,
        provider_config_key="CODE_GEN_PROVIDER",
        mock_value="mock",
        real_values=["aider", "openhands", "opencode"],
        default_real_value="aider",
        pip_dependencies=["aider-chat"],
        env_keys_required=["DEEPSEEK_API_KEY", "QWEN_API_KEY"],
        services_required=[],
        description="Aider终端原生编程 / OpenHands自主Agent / OpenCode",
        depends_on=["llm"],
        parallel_group="delivery",
    ),
    "memory": ModuleDef(
        name="memory",
        display_name="记忆系统层",
        priority=5,
        provider_config_key="MEMORY_PROVIDER",
        mock_value="mock",
        real_values=["mem0", "zep", "hybrid"],
        default_real_value="mem0",
        pip_dependencies=["mem0ai"],
        env_keys_required=["DEEPSEEK_API_KEY", "QWEN_API_KEY"],
        services_required=[],
        description="Mem0智能记忆 / Zep Graphiti时序知识图谱",
        depends_on=["llm"],
        parallel_group="memory",
    ),
}

# 切换顺序（按优先级）
SWITCH_ORDER = sorted(MODULES.keys(), key=lambda k: MODULES[k].priority)


# ============================================
# 环境变量文件操作
# ============================================

def load_env_file(env_path: Path) -> dict[str, str]:
    """加载.env文件为字典"""
    env = {}
    if not env_path.exists():
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def save_env_file(env_path: Path, env: dict[str, str]):
    """保存字典到.env文件，保留注释和顺序"""
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        updated_keys = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in env:
                    new_lines.append(f"{key}={env[key]}")
                    updated_keys.add(key)
                    continue
            new_lines.append(line)
        # 添加新的key
        for key, value in env.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={value}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        # 从.example复制
        if ENV_EXAMPLE.exists():
            shutil.copy(ENV_EXAMPLE, env_path)
            env = load_env_file(env_path)
            save_env_file(env_path, env)
        else:
            with open(env_path, "w") as f:
                for key, value in env.items():
                    f.write(f"{key}={value}\n")


def backup_env_file(env_path: Path, module_name: str) -> Path:
    """备份.env文件"""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f".env.{module_name}.{timestamp}.bak"
    if env_path.exists():
        shutil.copy(env_path, backup_path)
    return backup_path


# ============================================
# 环境检测
# ============================================

@dataclass
class ModuleStatus:
    """模块状态"""
    module: ModuleDef
    current_provider: str = ""
    is_mock: bool = True
    pip_installed: dict[str, bool] = field(default_factory=dict)
    env_configured: dict[str, bool] = field(default_factory=dict)
    services_running: dict[str, bool] = field(default_factory=dict)
    ready: bool = False
    issues: list[str] = field(default_factory=list)


def check_pip_package(package: str) -> bool:
    """检查pip包是否已安装"""
    try:
        # 处理包名和导入名不一致的情况
        import_name = package.replace("-", "_").replace(".", "_")
        # 特殊映射
        special_map = {
            "aider_chat": "aider",
            "mem0ai": "mem0",
            "marker_pdf": "marker",
        }
        import_name = special_map.get(import_name, import_name)
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def check_env_key(env: dict[str, str], keys: list[str], require_all: bool = False) -> tuple[bool, dict[str, bool]]:
    """检查环境变量是否配置（至少一个或全部）"""
    status = {k: bool(env.get(k, "")) for k in keys}
    if require_all:
        return all(status.values()), status
    else:
        return any(status.values()), status


def check_service_running(service_name: str) -> bool:
    """检查Docker服务是否运行"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        return service_name in result.stdout
    except Exception:
        return False


def detect_module_status(module: ModuleDef, env: dict[str, str]) -> ModuleStatus:
    """检测单个模块的状态"""
    status = ModuleStatus(module=module)
    status.current_provider = env.get(module.provider_config_key, module.mock_value)
    status.is_mock = status.current_provider == module.mock_value

    # 检查pip依赖
    for pkg in module.pip_dependencies:
        status.pip_installed[pkg] = check_pip_package(pkg)

    # 检查环境变量
    if module.env_keys_required:
        _, status.env_configured = check_env_key(env, module.env_keys_required)

    # 检查服务
    for svc in module.services_required:
        status.services_running[svc] = check_service_running(svc)

    # 判断是否就绪
    issues = []
    if not all(status.pip_installed.values()):
        missing = [k for k, v in status.pip_installed.items() if not v]
        issues.append(f"缺少pip依赖: {', '.join(missing)}")
    if module.env_keys_required and not any(status.env_configured.values()):
        issues.append(f"缺少API Key配置: {', '.join(module.env_keys_required)}")
    if not all(status.services_running.values()):
        missing = [k for k, v in status.services_running.items() if not v]
        issues.append(f"服务未运行: {', '.join(missing)}")

    status.issues = issues
    status.ready = len(issues) == 0
    return status


def detect_all_modules(env: dict[str, str]) -> dict[str, ModuleStatus]:
    """检测所有模块状态（并行加速）"""
    results = {}
    for name, module in MODULES.items():
        results[name] = detect_module_status(module, env)
    return results


# ============================================
# 依赖安装
# ============================================

def install_pip_packages(packages: list[str], verbose: bool = False) -> tuple[bool, str]:
    """安装pip包"""
    if not packages:
        return True, "无需安装"
    cmd = [sys.executable, "-m", "pip", "install", "-q"] + packages
    if verbose:
        print(f"  执行: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            return True, f"安装成功: {', '.join(packages)}"
        else:
            return False, f"安装失败: {result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return False, "安装超时（300秒）"
    except Exception as e:
        return False, f"安装异常: {e}"


# ============================================
# 模块验证
# ============================================

async def verify_module(module_name: str, env: dict[str, str]) -> tuple[bool, str]:
    """验证模块是否正常工作"""
    import tempfile
    os.environ["MEMORY_STORAGE_DIR"] = tempfile.mkdtemp()
    os.environ["OPENHANDS_WORKSPACE_BASE"] = tempfile.mkdtemp()

    try:
        if module_name == "llm":
            from src.llm import get_llm_client, LLMMessage
            client = get_llm_client("verify")
            resp = await client.chat([LLMMessage("user", "说'OK'")], temperature=0.1)
            if resp.finish_reason == "error":
                return False, f"LLM调用失败: {resp.content[:200]}"
            return True, f"LLM调用成功，模型={resp.model}，延迟={resp.latency_ms:.0f}ms"

        elif module_name == "doc_parser":
            from src.tools.doc_parser import DocParserTool
            tool = DocParserTool()
            test_file = "/tmp/verify_doc.txt"
            with open(test_file, "w") as f:
                f.write("验证文档解析功能")
            result = await tool.parse(test_file)
            if not result["success"]:
                return False, f"文档解析失败: {result.get('error', '')}"
            return True, f"文档解析成功，provider={result.get('provider', '')}，块数={len(result.get('structured', []))}"

        elif module_name == "knowledge_base":
            from src.tools.knowledge_base import KnowledgeBaseTool
            kb = KnowledgeBaseTool("verify")
            await kb.create("verify_kb")
            await kb.add_documents("kb_verify_verify_kb", [{"content": "验证知识库功能", "filename": "test.pdf"}])
            result = await kb.query("kb_verify_verify_kb", "验证")
            if not result["success"]:
                return False, "知识库查询失败"
            return True, f"知识库查询成功，模式={result.get('retrieval_mode', '')}，结果数={len(result.get('answers', []))}"

        elif module_name == "evaluation":
            from src.evaluation.evaluator import Evaluator
            evaluator = Evaluator("verify")
            result = await evaluator.evaluate_output(
                input_text="业务流程有哪些？",
                output_text="业务流程包括受理、审核、处理。",
                expected_output="业务流程包括受理、审核、处理",
                context="业务流程包括受理、审核、处理三个环节。",
            )
            if "scores" not in result:
                return False, "评测结果格式错误"
            return True, f"评测成功，通过={result['passed']}，指标数={len(result['scores'])}"

        elif module_name == "code_gen":
            from src.tools.code_gen import CodeGenTool
            cg = CodeGenTool("verify")
            result = await cg.generate_project(
                requirements=[{"id": "R1", "title": "验证", "description": "验证代码生成"}],
                tech_stack={"backend": "FastAPI"},
                project_name="verify_proj",
            )
            if not result["success"]:
                return False, "代码生成失败"
            return True, f"代码生成成功，provider={result.get('provider', '')}，文件数={result.get('files_generated', 0)}"

        elif module_name == "memory":
            from src.memory import MemoryManager
            memory = MemoryManager.get_instance("verify")
            item = await memory.remember("验证记忆系统功能", memory_type="fact", importance=0.9)
            results = await memory.recall("验证", limit=3)
            if item is None or len(results) == 0:
                return False, "记忆系统验证失败"
            return True, f"记忆系统正常，记忆数={len(results)}，实体数={memory.get_stats()['entities_count']}"

        else:
            return False, f"未知模块: {module_name}"

    except Exception as e:
        return False, f"验证异常: {type(e).__name__}: {e}"


# ============================================
# 切换执行
# ============================================

@dataclass
class SwitchResult:
    """切换结果"""
    module_name: str
    success: bool
    action: str  # switch / rollback / verify
    message: str
    duration_seconds: float = 0.0
    details: dict = field(default_factory=dict)


async def switch_module(
    module_name: str,
    env_path: Path,
    auto_install: bool = False,
    skip_verify: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> SwitchResult:
    """切换单个模块到真实实现"""
    start = time.time()
    module = MODULES[module_name]
    env = load_env_file(env_path)

    print(f"\n{'='*60}")
    print(f"切换模块: {module.display_name} ({module_name})")
    print(f"{'='*60}")

    # 检查依赖
    status = detect_module_status(module, env)
    print(f"  当前provider: {status.current_provider}")
    pip_str = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in status.pip_installed.items()) or "无"
    print(f"  pip依赖: {pip_str}")
    if module.env_keys_required:
        env_str = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in status.env_configured.items())
        print(f"  API Key: {env_str}")
    if module.services_required:
        svc_str = ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in status.services_running.items())
        print(f"  服务: {svc_str}")

    if status.issues:
        print(f"  未就绪项:")
        for issue in status.issues:
            print(f"    - {issue}")

    # 自动安装依赖
    if auto_install and not all(status.pip_installed.values()):
        missing = [k for k, v in status.pip_installed.items() if not v]
        print(f"\n  自动安装依赖: {', '.join(missing)}")
        if not dry_run:
            ok, msg = install_pip_packages(missing, verbose)
            print(f"  {msg}")
            if not ok:
                return SwitchResult(module_name, False, "switch", f"依赖安装失败: {msg}", time.time() - start)
            # 重新检测
            status = detect_module_status(module, load_env_file(env_path))

    # 检查是否就绪
    if not status.ready:
        msg = f"模块未就绪，无法切换: {'; '.join(status.issues)}"
        print(f"\n  ✗ {msg}")
        return SwitchResult(module_name, False, "switch", msg, time.time() - start)

    if dry_run:
        msg = f"Dry-run: 模块就绪，将切换到 {module.default_real_value}"
        print(f"\n  ✓ {msg}")
        return SwitchResult(module_name, True, "switch", msg, time.time() - start,
                            details={"target_provider": module.default_real_value})

    # 备份并切换
    backup_path = backup_env_file(env_path, module_name)
    print(f"\n  备份配置: {backup_path.name}")

    env[module.provider_config_key] = module.default_real_value
    save_env_file(env_path, env)
    print(f"  切换provider: {status.current_provider} → {module.default_real_value}")

    # 验证
    if not skip_verify:
        print(f"  运行验证...")
        # 重新加载环境变量
        for k, v in env.items():
            os.environ[k] = v
        ok, msg = await verify_module(module_name, env)
        print(f"  验证结果: {'✓' if ok else '✗'} {msg}")
        if not ok:
            # 验证失败，自动回滚
            print(f"  验证失败，自动回滚...")
            shutil.copy(backup_path, env_path)
            return SwitchResult(module_name, False, "switch", f"验证失败已回滚: {msg}",
                                time.time() - start, details={"backup": str(backup_path)})
    else:
        print(f"  跳过验证（--skip-verify）")

    duration = time.time() - start
    msg = f"切换成功: {module.display_name} → {module.default_real_value}（{duration:.1f}s）"
    print(f"\n  ✓ {msg}")
    return SwitchResult(module_name, True, "switch", msg, duration,
                        details={"target_provider": module.default_real_value, "backup": str(backup_path)})


async def rollback_module(
    module_name: str,
    env_path: Path,
    skip_verify: bool = False,
    verbose: bool = False,
) -> SwitchResult:
    """回滚单个模块到mock"""
    start = time.time()
    module = MODULES[module_name]
    env = load_env_file(env_path)
    current = env.get(module.provider_config_key, module.mock_value)

    print(f"\n回滚模块: {module.display_name} ({module_name})")
    print(f"  当前provider: {current}")

    if current == module.mock_value:
        msg = f"模块已是mock模式，无需回滚"
        print(f"  ✓ {msg}")
        return SwitchResult(module_name, True, "rollback", msg, time.time() - start)

    backup_path = backup_env_file(env_path, f"{module_name}_rollback")
    env[module.provider_config_key] = module.mock_value
    save_env_file(env_path, env)
    print(f"  回滚provider: {current} → {module.mock_value}")

    duration = time.time() - start
    msg = f"回滚成功: {module.display_name} → mock（{duration:.1f}s）"
    print(f"  ✓ {msg}")
    return SwitchResult(module_name, True, "rollback", msg, duration,
                        details={"backup": str(backup_path)})


# ============================================
# 报告生成
# ============================================

def generate_report(results: list[SwitchResult], env_path: Path) -> str:
    """生成切换报告"""
    env = load_env_file(env_path)
    lines = []
    lines.append("# AI-FDE Engine 模块切换报告")
    lines.append(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"配置文件: {env_path}")
    lines.append(f"\n## 切换结果汇总\n")
    lines.append(f"| 模块 | 动作 | 结果 | 耗时 | 详情 |")
    lines.append(f"|------|------|------|------|------|")
    for r in results:
        status_icon = "✓" if r.success else "✗"
        lines.append(f"| {MODULES[r.module_name].display_name} | {r.action} | {status_icon} | {r.duration_seconds:.1f}s | {r.message[:60]} |")

    success_count = sum(1 for r in results if r.success)
    lines.append(f"\n**总计: {success_count}/{len(results)} 成功**")

    lines.append(f"\n## 当前配置状态\n")
    for name in SWITCH_ORDER:
        module = MODULES[name]
        provider = env.get(module.provider_config_key, module.mock_value)
        is_mock = provider == module.mock_value
        lines.append(f"- **{module.display_name}**: `{provider}` {'(mock)' if is_mock else '(真实)'}")

    lines.append(f"\n## 下一步建议\n")
    real_modules = [name for name in SWITCH_ORDER if env.get(MODULES[name].provider_config_key, MODULES[name].mock_value) != MODULES[name].mock_value]
    mock_modules = [name for name in SWITCH_ORDER if env.get(MODULES[name].provider_config_key, MODULES[name].mock_value) == MODULES[name].mock_value]
    if mock_modules:
        lines.append(f"仍有 {len(mock_modules)} 个模块为mock模式: {', '.join(mock_modules)}")
        lines.append(f"运行 `python switch_modules.py run --all` 继续切换")
    else:
        lines.append("所有模块已切换为真实实现！")
        lines.append("运行 `python demo_e2e.py` 进行端到端验证")

    return "\n".join(lines)


# ============================================
# 命令处理
# ============================================

def cmd_status(args):
    """查看状态"""
    env = load_env_file(args.env_file)
    print("\n" + "="*70)
    print("  AI-FDE Engine 模块状态")
    print("="*70)
    print(f"\n{'模块':<16} {'当前Provider':<14} {'状态':<8} {'就绪':<6} {'问题'}")
    print("-"*70)
    for name in SWITCH_ORDER:
        module = MODULES[name]
        status = detect_module_status(module, env)
        state = "MOCK" if status.is_mock else "真实"
        ready = "✓" if status.ready else "✗"
        issues = "; ".join(status.issues[:2]) if status.issues else "-"
        print(f"{module.display_name:<16} {status.current_provider:<14} {state:<8} {ready:<6} {issues}")

    real_count = sum(1 for name in SWITCH_ORDER if env.get(MODULES[name].provider_config_key, MODULES[name].mock_value) != MODULES[name].mock_value)
    print(f"\n已切换真实模块: {real_count}/{len(SWITCH_ORDER)}")


def cmd_check(args):
    """检测环境"""
    env = load_env_file(args.env_file)
    print("\n环境就绪检测:")
    all_ready = True
    for name in SWITCH_ORDER:
        module = MODULES[name]
        status = detect_module_status(module, env)
        icon = "✓" if status.ready else "✗"
        print(f"\n  {icon} {module.display_name}")
        if status.issues:
            all_ready = False
            for issue in status.issues:
                print(f"    - {issue}")
        else:
            print(f"    就绪，可切换到 {module.default_real_value}")
    print(f"\n总体: {'全部就绪' if all_ready else '存在未就绪项'}")


async def cmd_run(args):
    """执行切换"""
    env_path = args.env_file
    if not env_path.exists():
        print(f"配置文件不存在: {env_path}")
        print(f"从 .env.example 复制...")
        env_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ENV_EXAMPLE, env_path)

    results = []

    if args.module:
        if args.module not in MODULES:
            print(f"未知模块: {args.module}")
            print(f"可用模块: {', '.join(SWITCH_ORDER)}")
            return
        modules_to_switch = [args.module]
    elif args.all:
        modules_to_switch = SWITCH_ORDER
    else:
        print("请指定 --module 或 --all")
        return

    if args.parallel and len(modules_to_switch) > 1:
        # 并行切换：按parallel_group分组，同组并行，不同组顺序
        print(f"\n并行模式: 按依赖关系分组切换")
        groups = {}
        for name in modules_to_switch:
            group = MODULES[name].parallel_group or name
            groups.setdefault(group, []).append(name)

        for group_name, group_modules in groups.items():
            print(f"\n--- 组: {group_name} ({', '.join(group_modules)}) ---")
            tasks = [switch_module(m, env_path, args.auto_install, args.skip_verify, args.dry_run, args.verbose)
                     for m in group_modules]
            group_results = await asyncio.gather(*tasks)
            results.extend(group_results)
    else:
        # 顺序切换
        for name in modules_to_switch:
            result = await switch_module(name, env_path, args.auto_install, args.skip_verify, args.dry_run, args.verbose)
            results.append(result)
            # 如果关键模块失败，停止后续
            if not result.success and name == "llm":
                print(f"\nLLM模块切换失败，停止后续切换（其他模块依赖LLM）")
                break

    # 生成报告
    print("\n" + "="*60)
    print("  切换完成")
    print("="*60)
    success = sum(1 for r in results if r.success)
    print(f"\n结果: {success}/{len(results)} 成功")
    for r in results:
        icon = "✓" if r.success else "✗"
        print(f"  {icon} {MODULES[r.module_name].display_name}: {r.message}")

    # 保存报告
    report = generate_report(results, env_path)
    report_path = PROJECT_ROOT / "switch_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_path}")


async def cmd_rollback(args):
    """回滚"""
    env_path = args.env_file
    results = []

    if args.module:
        if args.module not in MODULES:
            print(f"未知模块: {args.module}")
            return
        modules_to_rollback = [args.module]
    elif args.all:
        # 逆序回滚
        modules_to_rollback = list(reversed(SWITCH_ORDER))
    else:
        print("请指定 --module 或 --all")
        return

    for name in modules_to_rollback:
        result = await rollback_module(name, env_path, args.skip_verify, args.verbose)
        results.append(result)

    print(f"\n回滚完成: {sum(1 for r in results if r.success)}/{len(results)} 成功")


async def cmd_verify(args):
    """验证"""
    env_path = args.env_file
    env = load_env_file(env_path)
    # 加载环境变量
    for k, v in env.items():
        os.environ[k] = v

    modules_to_verify = [args.module] if args.module else SWITCH_ORDER
    print("\n模块验证:")
    for name in modules_to_verify:
        if name not in MODULES:
            print(f"  未知模块: {name}")
            continue
        module = MODULES[name]
        provider = env.get(module.provider_config_key, module.mock_value)
        print(f"\n  验证 {module.display_name} (provider={provider})...")
        ok, msg = await verify_module(name, env)
        icon = "✓" if ok else "✗"
        print(f"    {icon} {msg}")


def cmd_report(args):
    """生成报告"""
    env_path = args.env_file
    env = load_env_file(env_path)
    results = []
    for name in SWITCH_ORDER:
        module = MODULES[name]
        provider = env.get(module.provider_config_key, module.mock_value)
        is_mock = provider == module.mock_value
        results.append(SwitchResult(
            module_name=name,
            success=not is_mock,
            action="status",
            message=f"当前provider={provider}",
        ))
    report = generate_report(results, env_path)
    print(report)
    report_path = PROJECT_ROOT / "switch_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_path}")


# ============================================
# 主入口
# ============================================

def main():
    parser = argparse.ArgumentParser(description="AI-FDE Engine 模块自动化切换工具")
    parser.add_argument("--env-file", type=Path, default=ENV_FILE_DEFAULT, help="env文件路径")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="查看模块状态")

    # check
    subparsers.add_parser("check", help="检测环境就绪情况")

    # run
    run_parser = subparsers.add_parser("run", help="切换模块到真实实现")
    run_parser.add_argument("--module", choices=list(MODULES.keys()), help="指定模块")
    run_parser.add_argument("--all", action="store_true", help="切换所有模块")
    run_parser.add_argument("--parallel", action="store_true", help="并行切换（加速）")
    run_parser.add_argument("--auto-install", action="store_true", help="自动安装缺失依赖")
    run_parser.add_argument("--skip-verify", action="store_true", help="跳过验证（加速）")
    run_parser.add_argument("--dry-run", action="store_true", help="只检测不执行")

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="回滚到mock")
    rollback_parser.add_argument("--module", choices=list(MODULES.keys()), help="指定模块")
    rollback_parser.add_argument("--all", action="store_true", help="回滚所有模块")
    rollback_parser.add_argument("--skip-verify", action="store_true", help="跳过验证")

    # verify
    verify_parser = subparsers.add_parser("verify", help="验证模块")
    verify_parser.add_argument("--module", choices=list(MODULES.keys()), help="指定模块")

    # report
    subparsers.add_parser("report", help="生成切换报告")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "check":
        cmd_check(args)
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "rollback":
        asyncio.run(cmd_rollback(args))
    elif args.command == "verify":
        asyncio.run(cmd_verify(args))
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
