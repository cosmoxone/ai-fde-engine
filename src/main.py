"""
AI-FDE Engine 主应用入口 - FastAPI
提供REST API + WebSocket，统一调度四大Agent
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.delivery import DeliveryAgent
from .agents.design import DesignAgent
from .agents.research import ResearchAgent
from .agents.self_service import SelfServiceAgent
from .agents.training import TrainingAgent
from .config import get_settings
from .evaluation.evaluator import Evaluator
from .exporter import build_deliverables, export_zip
from .memory import get_memory_manager
from .pipeline.iteration import NightlyIterationPipeline
from .storage import get_storage
from .templates import build_research_context, list_templates, match_template
from .tools.benchmark import BenchmarkTool
from .tools.doc_parser import DocParserTool

settings = get_settings()

# 业务数据持久化：storage 扩展点（默认 SQLite 单文件 data/aifde.db，v0.1.1 A1）
# 运行时 Agent 实例保持内存态（重建成本低，不参与持久化）
_self_service_agents: dict[str, SelfServiceAgent] = {}


def _add_to_review_queue(project_id: str, review_type: str, result: Any = None, requires_approval: bool = True):
    """
    后台异步任务完成后，自动加入审核队列
    实现"后台默默干活，完成后通知人工审核"的闭环
    """
    import time as _time

    review_item = {
        "review_id": f"rev-{uuid.uuid4().hex[:8]}",
        "project_id": project_id,
        "type": review_type,
        "status": "pending" if requires_approval else "auto_approved",
        "created_at": _time.time(),
        "result": result.to_dict() if hasattr(result, "to_dict") else result,
        "requires_approval": requires_approval,
    }
    return get_storage().add_review(review_item)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化
    os.makedirs(settings.openhands_workspace_base, exist_ok=True)
    os.makedirs(os.environ.get("MEMORY_STORAGE_DIR", "/tmp/aifde-memory"), exist_ok=True)
    # 加载 Web 端保存的运行时设置（v0.1.1 A3：data/settings.json → 热恢复）
    from .settings_runtime import load_runtime_settings

    load_runtime_settings()
    yield
    # 关闭时清理


app = FastAPI(
    title=settings.app_name,
    version="0.1.3",
    description="AI驱动的FDE交付引擎 - 调研、设计、开发、迭代全流程AI化",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 静态文件与Dashboard =====
_static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/")
async def root():
    """根路径重定向到Dashboard"""
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
async def dashboard():
    """FDE交付控制台Dashboard"""
    dashboard_path = os.path.join(_static_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"success": False, "error": "Dashboard文件不存在，请确认static/dashboard.html已部署"}


# ===== 请求模型 =====
class ProjectCreate(BaseModel):
    name: str
    client_name: Optional[str] = ""
    industry: Optional[str] = ""
    description: Optional[str] = ""


class ResearchRun(BaseModel):
    client_requirements: Optional[str] = ""
    interview_notes: Optional[str] = ""


class DesignRun(BaseModel):
    requirements_baseline: Optional[dict] = None


class DeliveryRun(BaseModel):
    task_type: str = "generate_code"
    tech_solution: Optional[dict] = None
    requirements: Optional[list] = None
    badcases: Optional[list] = None


class IterationRun(BaseModel):
    badcases: list[dict]
    benchmark_cases: Optional[list[dict]] = None


class BadcaseFeedback(BaseModel):
    input: str
    actual_output: str
    expected_output: Optional[str] = ""
    error_type: Optional[str] = ""
    severity: Optional[str] = "major"


# ===== 自助交付（F7）请求模型 =====
class OpportunityIdentifyRequest(BaseModel):
    business_description: str
    industry: Optional[str] = ""
    pain_points: Optional[list[str]] = []


class RequirementEditRequest(BaseModel):
    """需求项编辑请求（v0.1.3 B4 可编辑确认流）"""

    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    acceptance_criteria: Optional[str] = None


class FeatureEditRequest(BaseModel):
    """产品功能项编辑请求（v0.1.3 B4）"""

    name: Optional[str] = None
    module: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None


class RequirementGuideRequest(BaseModel):
    action: str = "generate_draft"  # generate_draft/confirm/modify/add
    requirement_draft: Optional[dict] = None
    user_feedback: Optional[str] = ""
    modified_requirements: Optional[dict] = None
    new_requirements: Optional[list[dict]] = None


class SolutionConfigRequest(BaseModel):
    selected_modules: list[str] = []
    deployment_mode: str = "saas"  # saas/private/hybrid
    integration_level: str = "basic"  # basic/standard/deep
    budget: Optional[float] = None


class PrototypeGenerateRequest(BaseModel):
    prototype_type: str = "knowledge_base_qa"
    config: Optional[dict] = None


class ValueCalculateRequest(BaseModel):
    baseline: Optional[dict] = None
    current: Optional[dict] = None
    investment: Optional[float] = 100000


class SelfServiceFeedback(BaseModel):
    feedback_type: str = "general"  # general/bug/suggestion/praise
    content: str
    rating: Optional[int] = 0
    prototype_id: Optional[str] = ""


class CompleteStepRequest(BaseModel):
    step_id: str
    confirmation: bool = False
    user_input: Optional[dict] = None


class ReviewActionRequest(BaseModel):
    action: str  # approve/reject
    comment: Optional[str] = ""
    reviewer: Optional[str] = ""


# ===== 健康检查 =====
# ===== 行业模板库（v0.1.2 B2）=====


@app.get("/api/v1/templates")
async def get_templates():
    """行业模板清单（内置：制造业质检/金融客服/政务问答）"""
    return {"success": True, "templates": list_templates()}


# ===== 运行时设置（v0.1.1 A3：Web配置引导）=====


class LLMSettingsRequest(BaseModel):
    """LLM Key 配置请求"""

    provider: str  # deepseek / qwen / openai / ollama / custom
    api_key: str
    base_url: Optional[str] = None


# ===== 交付物导出（v0.1.2 B1）=====


@app.get("/api/v1/projects/{project_id}/export/list")
async def list_exportables(project_id: str):
    """可导出的交付物清单"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    items = build_deliverables(project_id)
    return {
        "success": True,
        "items": [{"key": d.key, "title": d.title, "size": len(d.markdown)} for d in items],
        "total": len(items),
    }


@app.get("/api/v1/projects/{project_id}/export")
async def export_project(project_id: str, format: str = "md", item: Optional[str] = None):
    """
    导出交付物。

    - format=md|docx：打包全部交付物为 zip
    - item=<key>：单项 markdown 文本（format=md 时）
    """
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if format not in ("md", "docx"):
        raise HTTPException(status_code=400, detail="format 仅支持 md/docx")

    if item:
        deliverables = {d.key: d for d in build_deliverables(project_id)}
        d = deliverables.get(item)
        if d is None:
            raise HTTPException(status_code=404, detail=f"交付物不存在: {item}")
        from urllib.parse import quote

        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            d.markdown,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (f"attachment; filename=deliverable.md; filename*=UTF-8''{quote(d.key)}.md")
            },
        )

    filename, content = export_zip(project_id, fmt=format)
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/settings/llm")
async def get_llm_settings():
    """获取 LLM 配置状态（Key 脱敏）"""
    from .settings_runtime import get_llm_status

    return {"success": True, "llm": get_llm_status()}


@app.post("/api/v1/settings/llm")
async def update_llm_settings(req: LLMSettingsRequest):
    """配置 LLM API Key（热生效，无需重启）"""
    from .settings_runtime import save_llm_settings

    try:
        status = save_llm_settings(provider=req.provider, api_key=req.api_key, base_url=req.base_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "llm": status, "message": "配置已保存并热生效"}


@app.get("/api/v1/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "0.1.3",
        "app_name": settings.app_name,
        "env": settings.app_env,
        "active_projects": len(get_storage().list_projects()),
        "active_tasks": get_storage().count_running_tasks(),
        "services": {
            "postgresql": "healthy" if settings.postgres_host else "mock",
            "qdrant": "healthy" if settings.qdrant_host else "mock",
            "llm_api": "configured" if settings.deepseek_api_key or settings.qwen_api_key else "mock_mode",
            "memory": "healthy",
        },
    }


# ===== 项目管理 =====
@app.post("/api/v1/projects")
async def create_project(req: ProjectCreate):
    """创建项目"""
    project_id = str(uuid.uuid4())
    project = {
        "id": project_id,
        "name": req.name,
        "client_name": req.client_name,
        "industry": req.industry,
        "description": req.description,
        "status": "research",
        "created_at": __import__("time").time(),
        "config": {},
    }
    get_storage().create_project(project)
    # 初始化记忆
    memory = get_memory_manager(project_id)
    await memory.remember(
        content=f"项目创建：{req.name}，客户：{req.client_name}，行业：{req.industry}",
        memory_type="event",
        importance=0.9,
    )
    return {"success": True, "project": project}


@app.get("/api/v1/projects")
async def list_projects():
    """项目列表"""
    projects = get_storage().list_projects()
    return {"success": True, "projects": projects, "total": len(projects)}


@app.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str):
    """项目详情"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    project = get_storage().get_project(project_id)
    memory = get_memory_manager(project_id)
    return {
        "success": True,
        "project": project,
        "documents_count": len(get_storage().list_documents(project_id)),
        "memory_stats": memory.get_stats(),
    }


# ===== 文档管理 =====
@app.post("/api/v1/projects/{project_id}/documents")
async def upload_document(project_id: str, file: UploadFile = File(...)):
    """上传文档"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 保存文件
    save_dir = os.path.join("/tmp/aifde-docs", project_id)
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, file.filename)
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # 解析文档
    parser = DocParserTool()
    parse_result = await parser.parse(save_path)

    doc_record = {
        "id": str(uuid.uuid4()),
        "filename": file.filename,
        "file_type": parse_result.get("file_type", ""),
        "file_size": len(content),
        "storage_path": save_path,
        "parse_status": "parsed" if parse_result.get("success") else "failed",
        "content": parse_result.get("content", ""),
        "structured": parse_result.get("structured", []),
        "page_count": parse_result.get("page_count", 0),
        "uploaded_at": __import__("time").time(),
    }
    get_storage().add_document(project_id, doc_record)

    # 记录到记忆
    memory = get_memory_manager(project_id)
    await memory.remember(
        content=f"上传文档：{file.filename}，{parse_result.get('page_count', 0)}页，解析状态：{doc_record['parse_status']}",
        memory_type="event",
    )

    return {"success": True, "document": doc_record, "parse_result": parse_result}


@app.get("/api/v1/projects/{project_id}/documents")
async def list_documents(project_id: str):
    """文档列表"""
    docs = get_storage().list_documents(project_id)
    return {"success": True, "documents": docs, "total": len(docs)}


# ===== 调研分析 =====
@app.post("/api/v1/projects/{project_id}/research/run")
async def run_research(project_id: str, req: ResearchRun, background_tasks: BackgroundTasks):
    """触发调研分析"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": "research",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_research():
        try:
            agent = ResearchAgent(project_id)
            docs = get_storage().list_documents(project_id)
            # v0.1.2 B2: 行业模板上下文注入（提升真实LLM输出贴合度）
            pack = match_template(get_storage().get_project(project_id).get("industry", ""))
            industry_ctx = build_research_context(pack) if pack else ""
            result = await agent.execute(
                {
                    "documents": docs,
                    "client_requirements": req.client_requirements,
                    "interview_notes": req.interview_notes,
                    "industry_context": industry_ctx,
                }
            )
            get_storage().update_task(task_id, {"status": "completed", "result": result.to_dict()})
            get_storage().update_project(
                project_id, {"requirements_baseline": result.structured_output, "status": "design"}
            )
            # 后台完成后自动入审核队列，等待人工确认
            _add_to_review_queue(project_id, "research_result", result, requires_approval=True)
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_research)
    return {"success": True, "task_id": task_id, "message": "调研分析已启动"}


# ===== 方案设计 =====
@app.post("/api/v1/projects/{project_id}/design/run")
async def run_design(project_id: str, req: DesignRun, background_tasks: BackgroundTasks):
    """触发方案设计"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": "design",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_design():
        try:
            agent = DesignAgent(project_id)
            baseline = req.requirements_baseline or (get_storage().get_project(project_id) or {}).get(
                "requirements_baseline", {}
            )
            result = await agent.execute(
                {
                    "requirements_baseline": baseline,
                    "business_process": baseline.get("business_process", {}),
                    "data_assets": baseline.get("data_assets", {}),
                    "benchmark": baseline.get("benchmark", {}),
                }
            )
            get_storage().update_task(task_id, {"status": "completed", "result": result.to_dict()})
            get_storage().update_project(project_id, {"solutions": result.structured_output, "status": "iteration"})
            # 后台完成后自动入审核队列
            _add_to_review_queue(project_id, "design_solution", result, requires_approval=True)
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_design)
    return {"success": True, "task_id": task_id, "message": "方案设计已启动"}


# ===== 开发交付 =====
@app.post("/api/v1/projects/{project_id}/delivery/run")
async def run_delivery(project_id: str, req: DeliveryRun, background_tasks: BackgroundTasks):
    """触发开发交付任务"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": f"delivery_{req.task_type}",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_delivery():
        try:
            agent = DeliveryAgent(project_id)
            result = await agent.execute(
                {
                    "task_type": req.task_type,
                    "tech_solution": req.tech_solution
                    or (get_storage().get_project(project_id) or {}).get("solutions", {}).get("tech_solution", {}),
                    "requirements": req.requirements
                    or (get_storage().get_project(project_id) or {})
                    .get("requirements_baseline", {})
                    .get("requirements", {})
                    .get("functional", []),
                    "badcases": req.badcases or [],
                    "project_name": (get_storage().get_project(project_id) or {}).get("name", ""),
                }
            )
            get_storage().update_task(task_id, {"status": "completed", "result": result.to_dict()})
            # 代码生成类任务完成后自动入审核队列（代码需要人工Review）
            if req.task_type in ("generate_code", "fix_badcase", "full_delivery"):
                _add_to_review_queue(project_id, f"delivery_{req.task_type}", result, requires_approval=True)
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_delivery)
    return {"success": True, "task_id": task_id, "message": f"开发交付任务[{req.task_type}]已启动"}


# ===== Benchmark =====
@app.post("/api/v1/projects/{project_id}/benchmarks/generate")
async def generate_benchmark(project_id: str, background_tasks: BackgroundTasks):
    """生成Benchmark测试集"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": "benchmark_generate",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_generate():
        try:
            tool = BenchmarkTool(project_id)
            docs = get_storage().list_documents(project_id)
            doc_contents = [{"content": d.get("content", ""), "filename": d.get("filename", "")} for d in docs]
            # v0.1.2 B2: 无业务文档时用行业模板种子用例打底（行业贴合度）
            pack = match_template(get_storage().get_project(project_id).get("industry", ""))
            seed = pack.benchmark_seed if pack and not doc_contents else None
            benchmark = await tool.generate(doc_contents, seed_cases=seed)
            get_storage().save_benchmark(benchmark)
            get_storage().update_task(
                task_id,
                {
                    "status": "completed",
                    "result": {
                        "benchmark_id": benchmark["benchmark_id"],
                        "case_count": benchmark["case_count"],
                    },
                },
            )
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_generate)
    return {"success": True, "task_id": task_id, "message": "Benchmark生成已启动"}


@app.get("/api/v1/projects/{project_id}/benchmarks")
async def list_benchmarks(project_id: str):
    """Benchmark列表"""
    bms = get_storage().list_benchmarks(project_id)
    return {"success": True, "benchmarks": bms, "total": len(bms)}


@app.post("/api/v1/projects/{project_id}/benchmarks/{benchmark_id}/run")
async def run_benchmark_eval(project_id: str, benchmark_id: str, background_tasks: BackgroundTasks):
    """跑Benchmark评测"""
    if get_storage().get_benchmark(benchmark_id) is None:
        raise HTTPException(status_code=404, detail="Benchmark不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": "benchmark_eval",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_eval():
        try:
            bm = get_storage().get_benchmark(benchmark_id)
            evaluator = Evaluator(project_id)
            result = await evaluator.run_benchmark(bm["test_cases"])
            gate_passed, failed_items = evaluator.check_quality_gate(result)
            get_storage().update_task(
                task_id,
                {
                    "status": "completed",
                    "result": {
                        **result.to_dict(),
                        "gate_passed": gate_passed,
                        "failed_items": failed_items,
                    },
                },
            )
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_eval)
    return {"success": True, "task_id": task_id, "message": "Benchmark评测已启动"}


# ===== 夜间迭代 =====
@app.post("/api/v1/projects/{project_id}/iteration/run")
async def run_iteration(project_id: str, req: IterationRun, background_tasks: BackgroundTasks):
    """触发夜间迭代"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    task_id = str(uuid.uuid4())
    get_storage().create_task(
        {
            "id": task_id,
            "project_id": project_id,
            "type": "nightly_iteration",
            "status": "running",
            "created_at": __import__("time").time(),
        }
    )

    async def do_iteration():
        try:
            storage = get_storage()
            badcases = req.badcases
            if not badcases:
                # v0.1.2 B5：自动归集本项目未处理badcase
                badcases = storage.list_badcases(project_id, status="open")
            pipeline = NightlyIterationPipeline(project_id)
            result = await pipeline.run(badcases, req.benchmark_cases)
            for bc in badcases:
                storage.update_badcase(bc.get("id", ""), {"status": "processed", "processed_version": result.version})
            get_storage().update_task(
                task_id,
                {
                    "status": "completed",
                    "result": {
                        "success": result.success,
                        "version": result.version,
                        "badcases_processed": result.badcases_processed,
                        "auto_fixed": result.auto_fixed,
                        "need_human": result.need_human,
                        "regression_accuracy": result.regression_accuracy,
                        "gate_passed": result.gate_passed,
                        "deployed": result.deployed,
                        "rolled_back": result.rolled_back,
                        "fix_suggestions": result.fix_suggestions,
                        "duration_seconds": result.duration_seconds,
                        "report": result.report,
                    },
                },
            )
        except Exception as e:
            get_storage().update_task(task_id, {"status": "failed", "error": str(e)})

    background_tasks.add_task(do_iteration)
    return {"success": True, "task_id": task_id, "message": "夜间迭代已启动"}


# ===== Badcase反馈 =====
@app.post("/api/v1/projects/{project_id}/badcases")
async def add_badcase(project_id: str, req: BadcaseFeedback):
    """提交Badcase反馈"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    badcase = {
        "id": str(uuid.uuid4()),
        "project_id": project_id,
        "input": req.input,
        "actual_output": req.actual_output,
        "expected_output": req.expected_output,
        "error_type": req.error_type,
        "severity": req.severity,
        "status": "open",
        "created_at": __import__("time").time(),
    }
    get_storage().add_badcase(badcase)  # v0.1.2 B5：badcase持久化，夜间迭代自动归集
    # 记录到记忆
    memory = get_memory_manager(project_id)
    await memory.remember(
        content=f"Badcase反馈：{req.input[:50]}... 错误类型：{req.error_type}，严重度：{req.severity}",
        memory_type="event",
        importance=0.7,
    )
    return {"success": True, "badcase": badcase}


# ===== 可编辑确认流（v0.1.3 B4）=====


@app.patch("/api/v1/projects/{project_id}/requirements/{req_id}")
async def edit_requirement(project_id: str, req_id: str, req: RequirementEditRequest):
    """
    编辑需求基线中的单个功能需求项（FDE 修改 AI 产出后再确认）。
    修改直接进入基线，导出交付物即包含修改后内容。
    """
    storage = get_storage()
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    baseline = project.get("requirements_baseline") or {}
    functional = (baseline.get("requirements") or {}).get("functional") or []
    target = next((r for r in functional if r.get("id") == req_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"需求项不存在: {req_id}")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates.get("priority") and updates["priority"] not in ("P0", "P1", "P2"):
        raise HTTPException(status_code=400, detail="priority 仅支持 P0/P1/P2")
    target.update(updates)

    storage.update_project(project_id, {"requirements_baseline": baseline})
    # 记录修改轨迹（记忆）
    memory = get_memory_manager(project_id)
    await memory.remember(
        content=f"需求项 {req_id} 已人工修改：{list(updates.keys())}",
        memory_type="event",
        importance=0.6,
    )
    return {"success": True, "requirement": target, "message": "修改已进入基线，导出交付物将包含最新内容"}


@app.patch("/api/v1/projects/{project_id}/solutions/features/{feature_id}")
async def edit_solution_feature(project_id: str, feature_id: str, req: FeatureEditRequest):
    """编辑产品方案中的单个功能项（v0.1.3 B4）"""
    storage = get_storage()
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    solutions = project.get("solutions") or {}
    features = (solutions.get("product_solution") or {}).get("features") or []
    target = next((f for f in features if f.get("id") == feature_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"功能项不存在: {feature_id}")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates.get("priority") and updates["priority"] not in ("P0", "P1", "P2"):
        raise HTTPException(status_code=400, detail="priority 仅支持 P0/P1/P2")
    target.update(updates)

    storage.update_project(project_id, {"solutions": solutions})
    return {"success": True, "feature": target}


@app.get("/api/v1/projects/{project_id}/badcases")
async def list_badcases(project_id: str, status: Optional[str] = None):
    """Badcase列表（v0.1.2 B5，可按状态过滤）"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    bcs = get_storage().list_badcases(project_id, status=status)
    return {"success": True, "badcases": bcs, "total": len(bcs)}


# ===== 记忆检索 =====
@app.get("/api/v1/projects/{project_id}/memory/search")
async def search_memory(project_id: str, query: str, limit: int = 10):
    """检索项目记忆"""
    memory = get_memory_manager(project_id)
    results = await memory.recall(query, limit=limit)
    return {
        "success": True,
        "query": query,
        "results": [m.to_dict() for m in results],
        "total": len(results),
    }


@app.get("/api/v1/projects/{project_id}/memory/stats")
async def memory_stats(project_id: str):
    """记忆统计"""
    memory = get_memory_manager(project_id)
    return {"success": True, "stats": memory.get_stats()}


@app.post("/api/v1/projects/{project_id}/memory/consolidate")
async def consolidate_memory(project_id: str):
    """触发记忆巩固"""
    memory = get_memory_manager(project_id)
    result = await memory.consolidate()
    return {"success": True, "result": result}


# ===== 自助交付（F7）=====


def _get_self_service_agent(project_id: str) -> SelfServiceAgent:
    """获取或创建自助服务Agent"""
    if project_id not in _self_service_agents:
        _self_service_agents[project_id] = SelfServiceAgent(project_id)
    return _self_service_agents[project_id]


@app.get("/api/v1/projects/{project_id}/self-service/progress")
async def get_self_service_progress(project_id: str):
    """获取自助交付引导进度"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    return {"success": True, "progress": agent.get_guidance_progress()}


@app.post("/api/v1/projects/{project_id}/self-service/opportunities")
async def identify_opportunities(project_id: str, req: OpportunityIdentifyRequest, background_tasks: BackgroundTasks):
    """AI落地机会识别"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    task_id = str(uuid.uuid4())
    get_storage().create_task({"task_id": task_id, "status": "running", "type": "identify_opportunities"})

    async def _run():
        result = await agent.run(
            {
                "task_type": "identify_opportunities",
                "business_description": req.business_description,
                "industry": req.industry,
                "pain_points": req.pain_points,
            }
        )
        get_storage().create_task(
            {
                "task_id": task_id,
                "status": "completed",
                "type": "identify_opportunities",
                "result": result.to_dict(),
            }
        )
        # 如果需要FDE审核，加入审核队列
        if result.metadata.get("needs_fde_review"):
            get_storage().add_review(
                {
                    "review_id": f"rev-{uuid.uuid4().hex[:8]}",
                    "project_id": project_id,
                    "type": "opportunity_identification",
                    "status": "pending",
                    "created_at": __import__("time").time(),
                }
            )

    background_tasks.add_task(_run)
    return {"success": True, "task_id": task_id, "message": "AI落地机会识别已启动"}


@app.post("/api/v1/projects/{project_id}/self-service/requirements")
async def guide_requirements(project_id: str, req: RequirementGuideRequest):
    """需求自助梳理（生成初稿/确认/修改/补充）"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "guide_requirement",
            "action": req.action,
            "requirement_draft": req.requirement_draft,
            "user_feedback": req.user_feedback,
            "modified_requirements": req.modified_requirements,
            "new_requirements": req.new_requirements,
        }
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"success": True, "result": result.structured_output}


@app.post("/api/v1/projects/{project_id}/self-service/solution")
async def configure_solution(project_id: str, req: SolutionConfigRequest):
    """方案自助配置"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "configure_solution",
            "selected_modules": req.selected_modules,
            "deployment_mode": req.deployment_mode,
            "integration_level": req.integration_level,
            "budget": req.budget,
        }
    )
    # 检测预算和功能模块偏离
    deviations = agent._detect_deviations(
        {
            "selected_modules": req.selected_modules,
            "budget": req.budget or 0,
        }
    )
    return {
        "success": True,
        "result": result.structured_output,
        "deviation_alerts": deviations,
    }


@app.post("/api/v1/projects/{project_id}/self-service/prototype")
async def generate_prototype(project_id: str, req: PrototypeGenerateRequest):
    """原型即时生成"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "generate_prototype",
            "prototype_type": req.prototype_type,
            "config": req.config,
        }
    )
    return {"success": True, "result": result.structured_output}


@app.get("/api/v1/projects/{project_id}/self-service/value")
async def get_value_dashboard(project_id: str):
    """获取价值仪表盘"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    # 如果还没有计算过价值，自动计算一次
    if not agent.value_metrics:
        result = await agent.run({"task_type": "calculate_value"})
        return {"success": True, "value": result.structured_output}
    return {
        "success": True,
        "value": {
            "metrics": [agent._metric_to_dict(m) for m in agent.value_metrics],
            "summary": {
                "average_improvement": sum(m.improvement_percentage for m in agent.value_metrics)
                / len(agent.value_metrics)
                if agent.value_metrics
                else 0,
            },
        },
    }


@app.post("/api/v1/projects/{project_id}/self-service/value/calculate")
async def calculate_value(project_id: str, req: ValueCalculateRequest):
    """计算价值指标"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "calculate_value",
            "baseline": req.baseline,
            "current": req.current,
            "investment": req.investment,
        }
    )
    return {"success": True, "result": result.structured_output}


@app.post("/api/v1/projects/{project_id}/self-service/feedback")
async def submit_self_service_feedback(project_id: str, req: SelfServiceFeedback):
    """提交自助服务反馈"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "submit_feedback",
            "feedback_type": req.feedback_type,
            "content": req.content,
            "rating": req.rating,
            "prototype_id": req.prototype_id,
        }
    )
    # 存储反馈
    get_storage().add_feedback(project_id, result.structured_output.get("feedback", {}))
    return {"success": True, "result": result.structured_output}


@app.get("/api/v1/projects/{project_id}/self-service/feedback")
async def list_self_service_feedback(project_id: str):
    """获取项目反馈列表"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True, "feedback": get_storage().list_feedback(project_id)}


@app.post("/api/v1/projects/{project_id}/self-service/complete-step")
async def complete_guidance_step(project_id: str, req: CompleteStepRequest):
    """完成引导步骤"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "complete_step",
            "step_id": req.step_id,
            "confirmation": req.confirmation,
            "user_input": req.user_input,
        }
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"success": True, "result": result.structured_output}


@app.get("/api/v1/projects/{project_id}/self-service/deviations")
async def get_deviation_alerts(project_id: str):
    """获取纠偏提醒列表"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    return {
        "success": True,
        "alerts": agent.deviation_alerts,
        "needs_immediate_attention": any(a.get("severity") == "high" for a in agent.deviation_alerts),
    }


# ===== F7 P1 增强功能 =====


@app.post("/api/v1/projects/{project_id}/self-service/training/push")
async def push_training_content(project_id: str):
    """F7.10 培训内容推送：基于客户当前阶段推送培训内容"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run({"task_type": "push_training"})
    return {"success": True, "result": result.structured_output}


@app.get("/api/v1/projects/{project_id}/self-service/maturity")
async def get_customer_maturity(project_id: str):
    """F7.11 客户成长路径：获取客户AI能力成熟度评估"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run({"task_type": "assess_maturity", "behavior": {}})
    return {"success": True, "result": result.structured_output}


@app.post("/api/v1/projects/{project_id}/self-service/maturity/assess")
async def assess_customer_maturity(project_id: str, req: dict):
    """F7.11 客户成长路径：基于行为数据评估成熟度"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run({"task_type": "assess_maturity", "behavior": req.get("behavior", {})})
    return {"success": True, "result": result.structured_output}


@app.get("/api/v1/projects/{project_id}/self-service/quote")
async def get_quote(project_id: str):
    """F7.12 付费转化引导：获取分阶段报价方案"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run({"task_type": "generate_quote"})
    return {"success": True, "result": result.structured_output}


@app.post("/api/v1/projects/{project_id}/self-service/communications")
async def log_communication(project_id: str, req: dict):
    """F7.13 客户沟通通道：记录沟通并生成摘要和行动项"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    agent = _get_self_service_agent(project_id)
    result = await agent.run(
        {
            "task_type": "log_communication",
            "type": req.get("type", "meeting"),
            "content": req.get("content", ""),
            "participants": req.get("participants", []),
        }
    )
    return {"success": True, "result": result.structured_output}


# ===== 后台Review工作台（FDE视角）=====


@app.get("/api/v1/self-service/review/pending")
async def list_pending_reviews():
    """获取待审核列表（FDE后台）"""
    pending = get_storage().list_reviews(status="pending")
    return {"success": True, "pending_count": len(pending), "reviews": pending}


@app.post("/api/v1/self-service/review/{review_id}/action")
async def review_action(review_id: str, req: ReviewActionRequest):
    """审核操作（通过/驳回）"""
    fields = {
        "status": "approved" if req.action == "approve" else "rejected",
        "comment": req.comment,
        "reviewer": req.reviewer,
    }
    review = get_storage().update_review(review_id, fields)
    if review is None:
        raise HTTPException(status_code=404, detail="审核项不存在")
    return {"success": True, "review": review}


@app.get("/api/v1/self-service/review/history")
async def list_review_history():
    """获取审核历史"""
    return {"success": True, "reviews": get_storage().list_reviews()}


# ===== F8 FDE培训成长模块 =====

_training_agents: dict[str, TrainingAgent] = {}


def _get_training_agent(learner_id: str) -> TrainingAgent:
    """获取或创建培训Agent"""
    if learner_id not in _training_agents:
        _training_agents[learner_id] = TrainingAgent(project_id="training", learner_id=learner_id)
    return _training_agents[learner_id]


@app.get("/api/v1/training/competency-model")
async def get_competency_model():
    """F8.1 获取FDE能力模型定义（三维度×五等级）"""
    agent = _get_training_agent("default")
    result = await agent.run({"task_type": "get_competency_model"})
    return {"success": True, "model": result.structured_output}


@app.post("/api/v1/training/assess")
async def assess_competency(req: dict):
    """F8.1+F8.7 能力评估：基于背景和表现评估FDE能力等级"""
    learner_id = req.get("learner_id", f"learner-{uuid.uuid4().hex[:8]}")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "assess_competency",
            "background": req.get("background", {}),
            "assessment": req.get("assessment", {}),
        }
    )
    return {"success": True, "learner_id": learner_id, "assessment": result.structured_output}


@app.post("/api/v1/training/learning-path")
async def generate_learning_path(req: dict):
    """F8.2 生成个性化学习路径（6周成长计划）"""
    learner_id = req.get("learner_id", f"learner-{uuid.uuid4().hex[:8]}")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "generate_learning_path",
            "target_level": req.get("target_level", "L3"),
            "current_level": req.get("current_level", "L1"),
            "background": req.get("background", {}),
        }
    )
    return {"success": True, "learner_id": learner_id, "learning_path": result.structured_output}


@app.post("/api/v1/training/coach/chat")
async def coach_chat(req: dict):
    """F8.3 AI教练对话辅导（7×24小时）"""
    learner_id = req.get("learner_id", "default")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "coach_chat",
            "message": req.get("message", ""),
            "context": req.get("context", {}),
            "conversation_id": req.get("conversation_id"),
        }
    )
    return {"success": True, "reply": result.structured_output}


@app.post("/api/v1/training/sandbox/start")
async def start_sandbox(req: dict):
    """F8.4 启动实战演练沙箱"""
    learner_id = req.get("learner_id", f"learner-{uuid.uuid4().hex[:8]}")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "start_sandbox",
            "scenario": req.get("scenario", "full_delivery"),
            "difficulty": req.get("difficulty", "beginner"),
        }
    )
    return {"success": True, "learner_id": learner_id, "sandbox": result.structured_output}


@app.post("/api/v1/training/sandbox/submit")
async def submit_sandbox_work(req: dict):
    """F8.4+F8.5 提交沙箱作业并获取AI即时点评"""
    learner_id = req.get("learner_id", "default")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "submit_sandbox_work",
            "sandbox_id": req.get("sandbox_id", ""),
            "task_id": req.get("task_id", ""),
            "work": req.get("work", ""),
        }
    )
    return {"success": True, "feedback": result.structured_output}


@app.post("/api/v1/training/feedback")
async def get_training_feedback(req: dict):
    """F8.5 获取操作即时反馈"""
    learner_id = req.get("learner_id", "default")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "get_feedback",
            "action": req.get("action", ""),
            "context": req.get("context", {}),
        }
    )
    return {"success": True, "feedback": result.structured_output}


@app.get("/api/v1/training/knowledge/search")
async def search_training_knowledge(query: str, category: str = "all"):
    """F8.6 搜索FDE知识库与案例库"""
    agent = _get_training_agent("default")
    result = await agent.run(
        {
            "task_type": "search_knowledge",
            "query": query,
            "category": category,
        }
    )
    return {"success": True, "results": result.structured_output}


@app.post("/api/v1/training/exam")
async def take_training_exam(req: dict):
    """F8.7 参加能力考核（通过后颁发认证）"""
    learner_id = req.get("learner_id", f"learner-{uuid.uuid4().hex[:8]}")
    agent = _get_training_agent(learner_id)
    result = await agent.run(
        {
            "task_type": "take_exam",
            "target_level": req.get("target_level", "L3"),
            "answers": req.get("answers", {}),
        }
    )
    return {"success": True, "learner_id": learner_id, "exam_result": result.structured_output}


@app.get("/api/v1/training/certifications")
async def get_certifications(learner_id: str = "default"):
    """F8.7 获取学员认证信息"""
    agent = _get_training_agent(learner_id)
    result = await agent.run({"task_type": "get_certification"})
    return {"success": True, "certifications": result.structured_output}


# ===== 任务状态 =====
@app.get("/api/v1/tasks/{task_id}")
async def get_task(task_id: str):
    """获取任务状态"""
    task = get_storage().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"success": True, "task": task}


@app.get("/api/v1/projects/{project_id}/tasks")
async def list_project_tasks(project_id: str):
    """项目任务列表"""
    tasks = get_storage().list_tasks(project_id)
    tasks.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"success": True, "tasks": tasks, "total": len(tasks)}


# ===== 项目进度 =====
@app.get("/api/v1/projects/{project_id}/progress")
async def project_progress(project_id: str):
    """项目进度"""
    if get_storage().get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    project = get_storage().get_project(project_id)
    tasks = get_storage().list_tasks(project_id)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    return {
        "success": True,
        "project_id": project_id,
        "project_name": project["name"],
        "status": project["status"],
        "total_tasks": len(tasks),
        "completed_tasks": completed,
        "progress": completed / len(tasks) if tasks else 0,
        "documents_count": len(get_storage().list_documents(project_id)),
        "has_requirements": "requirements_baseline" in project,
        "has_solutions": "solutions" in project,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.app_port)
