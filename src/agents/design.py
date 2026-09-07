"""
方案设计Agent - 负责产品方案、技术方案、验证方案的并行生成
模型：DeepSeek V4 Pro（逻辑推理+代码生成一体化）
"""
from __future__ import annotations

from typing import Any

from .base import BaseAgent, AgentResult


class DesignAgent(BaseAgent):
    """方案设计Agent：三方案并行生成，输出可执行方案+代码骨架"""

    agent_type = "design"
    agent_name = "方案设计Agent"
    description = "负责产品方案、技术方案、验证方案的设计与交叉校验"

    def __init__(self, project_id: str, **kwargs):
        kwargs.setdefault("model_task", "design")
        super().__init__(project_id, **kwargs)

    def get_system_prompt(self) -> str:
        return """你是一位资深的AI解决方案架构师，负责FDE项目的方案设计。

你的核心职责：
1. 产品方案设计：功能架构、用户交互流程、角色权限、MVP范围与迭代路线
2. 技术方案设计：技术选型、系统架构、数据流、接口清单、部署方案、风险评估
3. 验证方案设计：测试计划、测试用例、验收标准、评测方法
4. 三方案交叉校验：确保产品/技术/验证方案一致性，识别冲突与风险

设计原则：
- 可执行优先：方案不是PPT，要能直接指导开发，输出代码骨架和部署配置
- 技术选型有据：每个选型给出量化依据（性能、成本、成熟度、适配度）
- 风险前置：主动识别技术风险、数据风险、合规风险，给出应对方案
- KISS原则：MVP阶段只保留必要组件，避免过度设计

输出格式要求：
- 产品方案：功能架构图(Mermaid) + 功能清单 + 交互流程 + 权限矩阵 + 迭代路线
- 技术方案：技术选型对比 + 系统架构图(Mermaid) + 数据流图 + 接口清单 + 部署方案 + 资源评估 + 风险清单
- 验证方案：测试策略 + 测试用例清单 + 验收标准 + 评测指标 + 上线检查清单
- 代码骨架：项目目录结构 + 核心模块代码框架 + 配置文件模板
"""

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """
        执行方案设计
        input_data: {
            "requirements_baseline": {...},  # 已确认的需求基线
            "business_process": {...},        # 业务流程
            "data_assets": {...},             # 数据资产
            "benchmark": {...},               # Benchmark
            "project_context": "...",         # 记忆上下文
        }
        """
        requirements = input_data.get("requirements_baseline", {})
        business_process = input_data.get("business_process", {})
        benchmark = input_data.get("benchmark", {})
        memory_context = input_data.get("_memory_context", "")

        # 1. 三方案并行设计
        design_result = await self._perform_design(
            requirements, business_process, benchmark, memory_context
        )

        # 2. 交叉校验
        cross_check = self._cross_validate(design_result)
        design_result["cross_check"] = cross_check

        return AgentResult(
            success=True,
            content=design_result.get("summary", ""),
            structured_output=design_result,
            metadata={
                "product_features": len(design_result.get("product_solution", {}).get("features", [])),
                "tech_interfaces": len(design_result.get("tech_solution", {}).get("interfaces", [])),
                "test_cases": len(design_result.get("validation_solution", {}).get("test_cases", [])),
                "cross_check_issues": len(cross_check.get("issues", [])),
            },
        )

    async def _perform_design(
        self,
        requirements: dict,
        business_process: dict,
        benchmark: dict,
        memory_context: str,
    ) -> dict[str, Any]:
        """执行三方案设计（调用LLM，MVP使用模拟）"""
        # 实际部署中调用LLM
        # MVP模拟结果
        return {
            "summary": "基于需求基线完成产品、技术、验证三方案设计，方案已通过交叉一致性校验。",
            "product_solution": {
                "name": "智能业务处理助手",
                "architecture_mermaid": """graph TD
    A[用户层] --> B[业务受理模块]
    A --> C[知识库问答模块]
    B --> D[智能审核引擎]
    D --> E[业务处理助手]
    E --> F[结果反馈模块]
    C --> G[知识图谱RAG]
    G --> H[文档管理]
    F --> I[人工复核台]
    I --> J[运营管理后台]""",
                "features": [
                    {"id": "F1", "name": "智能资料审核", "module": "智能审核引擎", "description": "自动审核资料完整性与合规性", "priority": "P0"},
                    {"id": "F2", "name": "业务处理建议", "module": "业务处理助手", "description": "基于规则和案例提供处理建议", "priority": "P0"},
                    {"id": "F3", "name": "知识库问答", "module": "知识库问答模块", "description": "自然语言查询业务知识", "priority": "P1"},
                    {"id": "F4", "name": "结果反馈生成", "module": "结果反馈模块", "description": "自动生成客户通知与归档", "priority": "P1"},
                    {"id": "F5", "name": "人工复核台", "module": "人工复核台", "description": "AI结果人工审核与修正", "priority": "P0"},
                    {"id": "F6", "name": "运营管理后台", "module": "运营管理后台", "description": "系统配置、数据统计、用户管理", "priority": "P1"},
                ],
                "interaction_flows": [
                    "客户提交资料 → 智能审核 → 审核结果反馈 → 人工确认 → 业务处理",
                    "业务人员提问 → 知识库检索 → 答案生成 → 反馈评价",
                ],
                "permission_matrix": {
                    "admin": ["全部功能", "系统配置", "用户管理"],
                    "business_user": ["业务处理", "知识库问答", "结果查看"],
                    "reviewer": ["人工复核", "结果修正", "质量统计"],
                    "viewer": ["只读查看"],
                },
                "iteration_roadmap": [
                    {"phase": "MVP", "duration": "2周", "features": ["F1", "F2", "F5"]},
                    {"phase": "V1.0", "duration": "4周", "features": ["F3", "F4", "F6"]},
                    {"phase": "V2.0", "duration": "8周", "features": ["多轮对话", "主动推荐", "自定义流程"]},
                ],
            },
            "tech_solution": {
                "tech_stack": {
                    "frontend": {"framework": "React 18 + TypeScript", "ui": "Ant Design 5", "state": "Zustand"},
                    "backend": {"framework": "FastAPI + Python 3.11", "agent": "Pydantic AI V2", "orm": "SQLAlchemy 2.0"},
                    "ai": {"models": "DeepSeek V4 Pro + Qwen3.6", "kb": "LightRAG + Qdrant", "doc_parser": "Marker v2"},
                    "data": {"database": "PostgreSQL 16 + pgvector", "cache": "Redis 7", "storage": "MinIO"},
                    "devops": {"container": "Docker + Docker Compose", "ci_cd": "GitHub Actions", "monitor": "LangFuse"},
                },
                "selection_rationale": [
                    {"component": "LightRAG", "choice": "vs 微软GraphRAG", "reason": "索引成本低80%，增量更新，部署简单，适合MVP快速迭代"},
                    {"component": "Qdrant", "choice": "vs Milvus", "reason": "Rust高性能，多租户，运维简单，FDE项目规模足够"},
                    {"component": "Pydantic AI V2", "choice": "vs LangGraph/CrewAI", "reason": "类型安全，Capabilities可组合，生产级持久化，减少输出不可控"},
                    {"component": "Marker v2", "choice": "vs Docling", "reason": "GPU 7.4页/秒，总分76.0超Docling 50.3，速度快2倍"},
                ],
                "architecture_mermaid": """graph TB
    subgraph 接入层
        Nginx[Nginx反向代理]
    end
    subgraph 应用层
        API[FastAPI服务]
        Agent[Pydantic AI Agent集群]
    end
    subgraph 能力层
        KB[LightRAG知识库]
        Parser[Marker文档解析]
        Eval[DeepEval评测]
        Memory[Zep记忆图谱]
    end
    subgraph 数据层
        PG[(PostgreSQL)]
        Qdrant[(Qdrant向量库)]
        MinIO[(MinIO对象存储)]
        Redis[(Redis缓存)]
    end
    Nginx --> API
    API --> Agent
    Agent --> KB
    Agent --> Parser
    Agent --> Eval
    Agent --> Memory
    KB --> Qdrant
    API --> PG
    API --> MinIO
    API --> Redis""",
                "data_flow": "文档上传 → Marker解析 → LightRAG建图谱 → Qdrant存向量；用户请求 → Agent检索知识库 → 生成回答 → DeepEval评测 → 记录记忆图谱",
                "interfaces": [
                    {"name": "文档上传API", "method": "POST", "path": "/api/v1/projects/{id}/documents", "description": "上传业务文档"},
                    {"name": "知识库问答API", "method": "POST", "path": "/api/v1/projects/{id}/kb/query", "description": "知识库自然语言问答"},
                    {"name": "智能审核API", "method": "POST", "path": "/api/v1/projects/{id}/review", "description": "提交资料智能审核"},
                    {"name": "Benchmark评测API", "method": "POST", "path": "/api/v1/projects/{id}/benchmarks/{bid}/run", "description": "跑Benchmark评测"},
                    {"name": "迭代触发API", "method": "POST", "path": "/api/v1/projects/{id}/iteration/run", "description": "触发夜间迭代"},
                ],
                "deployment": {
                    "mode": "Docker Compose单机部署",
                    "services": ["nginx", "api", "postgresql", "qdrant", "minio", "redis"],
                    "resource_estimate": {"cpu": "8核", "memory": "32GB", "disk": "200GB SSD", "gpu": "可选1×A100"},
                    "scaling": "MVP单机，生产可拆分为微服务+K8s",
                },
                "risks": [
                    {"risk": "LLM API不稳定", "impact": "服务响应延迟或失败", "mitigation": "多模型兜底+重试机制+本地模型备选"},
                    {"risk": "知识库效果不达预期", "impact": "问答准确率低", "mitigation": "LightRAG+人工校对+持续迭代优化"},
                    {"risk": "客户数据安全", "impact": "数据泄露风险", "mitigation": "私有化部署+加密+权限隔离+沙箱"},
                ],
            },
            "validation_solution": {
                "test_strategy": "三层测试：单元测试(模块级) + 集成测试(流程级) + AI专项评测(输出质量)",
                "test_cases": [
                    {"id": "TC1", "name": "文档解析准确率", "type": "集成", "target": "表格/标题/段落识别准确率≥90%"},
                    {"id": "TC2", "name": "知识库问答准确率", "type": "AI评测", "target": "Benchmark准确率≥80%"},
                    {"id": "TC3", "name": "智能审核准确率", "type": "AI评测", "target": "资料完整性识别≥85%"},
                    {"id": "TC4", "name": "幻觉率控制", "type": "AI评测", "target": "幻觉率≤10%"},
                    {"id": "TC5", "name": "API响应性能", "type": "性能", "target": "P95≤3秒，复杂推理≤30秒"},
                    {"id": "TC6", "name": "并发稳定性", "type": "性能", "target": "50并发无失败"},
                    {"id": "TC7", "name": "Prompt注入防护", "type": "安全", "target": "恶意注入拦截率100%"},
                    {"id": "TC8", "name": "数据加密验证", "type": "安全", "target": "存储传输均AES-256加密"},
                ],
                "acceptance_criteria": {
                    "functional": "P0需求全部实现，端到端流程跑通",
                    "quality": "需求基线准确率≥80%，代码可运行率≥70%",
                    "performance": "核心性能指标达标",
                    "security": "无高危安全漏洞",
                },
                "evaluation_metrics": ["准确率", "幻觉率", "召回率", "响应时间", "Token成本", "用户满意度"],
                "launch_checklist": [
                    "功能测试全部通过", "性能测试达标", "安全审计通过",
                    "Benchmark验收通过", "部署文档齐全", "用户培训完成",
                    "回滚方案验证", "监控告警配置",
                ],
            },
            "code_skeleton": {
                "project_structure": """project/
├── frontend/               # React前端
│   ├── src/
│   │   ├── pages/         # 页面组件
│   │   ├── components/    # 通用组件
│   │   ├── services/      # API服务
│   │   └── store/         # 状态管理
│   └── package.json
├── backend/                # FastAPI后端
│   ├── app/
│   │   ├── api/           # 路由
│   │   ├── agents/        # Agent定义
│   │   ├── core/          # 配置/安全
│   │   ├── models/        # 数据模型
│   │   ├── schemas/       # Pydantic模式
│   │   └── services/      # 业务逻辑
│   ├── tests/
│   └── requirements.txt
├── deploy/                 # 部署配置
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── nginx.conf
└── docs/                   # 项目文档""",
                "core_modules": ["agents/", "services/kb_service.py", "services/review_service.py", "api/v1/endpoints.py"],
                "config_templates": ["docker-compose.yml", ".env.example", "alembic.ini"],
            },
        }

    def _cross_validate(self, design: dict) -> dict:
        """三方案交叉校验"""
        issues = []
        product_features = {f["id"] for f in design.get("product_solution", {}).get("features", [])}
        tech_interfaces = design.get("tech_solution", {}).get("interfaces", [])
        test_cases = design.get("validation_solution", {}).get("test_cases", [])

        # 校验：产品功能是否都有对应接口
        if len(product_features) > 0 and len(tech_interfaces) < len(product_features) // 2:
            issues.append("部分产品功能缺少对应API接口设计")

        # 校验：验收标准是否有对应测试用例
        if len(test_cases) < 5:
            issues.append("测试用例覆盖不足")

        # 校验：技术方案风险是否有应对措施
        risks = design.get("tech_solution", {}).get("risks", [])
        for r in risks:
            if not r.get("mitigation"):
                issues.append(f"风险[{r.get('risk')}]缺少应对措施")

        return {
            "consistent": len(issues) == 0,
            "issues": issues,
            "checked_at": "design_agent",
            "summary": "三方案一致性校验完成" if not issues else f"发现{len(issues)}个待优化项",
        }
