"""
自助服务Agent - 服务于自助型客户角色
核心能力：引导式项目创建、AI落地机会识别、需求自助梳理、方案自助配置、原型生成、智能纠偏
设计理念：非技术用户友好、Agent全程引导、后台实时赋能
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .base import BaseAgent, AgentResult, AgentCapability


@dataclass
class GuidanceStep:
    """引导步骤"""
    step_id: str
    step_name: str
    description: str
    order: int
    required: bool = True
    completed: bool = False
    user_input: dict[str, Any] = field(default_factory=dict)
    ai_output: Optional[dict[str, Any]] = None
    feedback: Optional[str] = None


@dataclass
class AIOpportunity:
    """AI落地机会"""
    opportunity_id: str
    title: str
    description: str
    business_scenario: str
    ai_approach: str
    estimated_efficiency_gain: float  # 百分比
    estimated_cost_saving: float  # 元/年
    implementation_difficulty: str  # low/medium/high
    priority: str  # high/medium/low
    roi_score: float  # 0-10


@dataclass
class ValueMetric:
    """价值指标"""
    metric_id: str
    name: str
    category: str  # efficiency/cost/quality/satisfaction
    current_value: float
    target_value: float
    unit: str
    improvement_percentage: float
    description: str


class SelfServiceAgent(BaseAgent):
    """
    自助服务Agent
    服务对象：自助型客户（非技术用户）
    工作方式：对话式引导 + 步骤化流程 + 实时反馈 + 后台赋能
    """

    agent_type = "self_service"
    agent_name = "自助服务Agent"
    description = "引导客户自主完成AI落地全过程，后台FDE实时赋能"

    def get_system_prompt(self) -> str:
        return """你是一位AI落地自助服务引导专家，服务于非技术背景的客户用户。

你的核心职责：
1. 引导式项目创建：通过对话式引导，帮助客户梳理业务痛点和AI落地机会
2. AI落地机会识别：基于客户业务描述，识别高ROI的AI应用场景
3. 需求自助梳理：生成需求初稿，引导客户通过确认/修改/补充完成需求基线
4. 方案自助配置：通过配置向导，帮助客户选择功能模块和部署方式
5. 原型即时生成：快速生成可试用的AI原型，让客户直观体验
6. 智能纠偏提醒：实时检测客户操作偏离最佳实践，给出改进建议
7. 价值量化展示：用数据展示AI落地带来的效率提升和成本节约

工作原则：
- 非技术用户友好：避免技术术语，用业务语言沟通
- 引导而非替代：引导客户思考和决策，不替客户做决定
- 实时反馈：操作即时反馈，问题即时提醒
- 后台赋能：关键节点自动触发FDE后台审核
- 价值导向：始终围绕业务价值展开，用数据说话

当前阶段：5周自助交付流程（启蒙→需求→方案→原型→决策）
"""

    def __init__(self, project_id: str, **kwargs):
        super().__init__(project_id, model_task="research", **kwargs)
        self.guidance_steps: list[GuidanceStep] = []
        self.opportunities: list[AIOpportunity] = []
        self.value_metrics: list[ValueMetric] = []
        self.deviation_alerts: list[dict[str, Any]] = []
        self._init_guidance_steps()

    def _init_guidance_steps(self):
        """初始化5周自助交付引导流程"""
        self.guidance_steps = [
            GuidanceStep(
                step_id="enlightenment",
                step_name="AI落地启蒙",
                description="通过对话梳理业务痛点，识别AI落地机会，生成ROI测算",
                order=1,
            ),
            GuidanceStep(
                step_id="requirement",
                step_name="需求自主梳理",
                description="上传业务资料，AI自动分析，客户通过确认/修改/补充完成需求基线",
                order=2,
            ),
            GuidanceStep(
                step_id="solution",
                step_name="方案自助配置",
                description="通过配置向导选择功能模块，AI生成技术方案和成本估算",
                order=3,
            ),
            GuidanceStep(
                step_id="prototype",
                step_name="原型试用验证",
                description="AI生成可试用原型，客户深度试用并反馈问题，AI自动优化",
                order=4,
            ),
            GuidanceStep(
                step_id="decision",
                step_name="价值确认与决策",
                description="查看价值仪表盘，生成正式开发方案和报价，做出付费决策",
                order=5,
            ),
        ]

    def _default_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="guidance_mode",
                description="引导模式：非技术用户友好的步骤化引导",
                before_run=self._guidance_before_run,
            ),
            AgentCapability(
                name="deviation_detection",
                description="智能纠偏：检测客户操作偏离最佳实践",
                after_run=self._deviation_after_run,
            ),
            AgentCapability(
                name="value_tracking",
                description="价值追踪：实时计算AI落地价值指标",
                after_run=self._value_after_run,
            ),
        ]

    def _guidance_before_run(self, agent: "BaseAgent", input_data: dict[str, Any]):
        """引导模式前置：检查当前步骤，提供引导信息"""
        current_step = self.get_current_step()
        if current_step and not input_data.get("skip_guidance"):
            input_data["_guidance_context"] = {
                "current_step": current_step.step_id,
                "step_name": current_step.step_name,
                "step_description": current_step.description,
                "step_order": current_step.order,
                "total_steps": len(self.guidance_steps),
                "progress_percentage": (current_step.order - 1) / len(self.guidance_steps) * 100,
            }

    def _deviation_after_run(self, agent: "BaseAgent", result: AgentResult) -> AgentResult:
        """纠偏检测后置：检测输出和操作是否偏离最佳实践"""
        if result.structured_output:
            alerts = self._detect_deviations(result.structured_output)
            if alerts:
                self.deviation_alerts.extend(alerts)
                result.metadata["deviation_alerts"] = alerts
                result.metadata["needs_fde_review"] = True
        return result

    def _value_after_run(self, agent: "BaseAgent", result: AgentResult) -> AgentResult:
        """价值追踪后置：更新价值指标"""
        if result.success and result.structured_output:
            self._update_value_metrics(result.structured_output)
        return result

    def get_current_step(self) -> Optional[GuidanceStep]:
        """获取当前引导步骤"""
        for step in self.guidance_steps:
            if not step.completed:
                return step
        return None

    def get_guidance_progress(self) -> dict[str, Any]:
        """获取引导进度"""
        completed = sum(1 for s in self.guidance_steps if s.completed)
        current = self.get_current_step()
        return {
            "total_steps": len(self.guidance_steps),
            "completed_steps": completed,
            "current_step": current.step_id if current else None,
            "current_step_name": current.step_name if current else None,
            "progress_percentage": completed / len(self.guidance_steps) * 100,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_name": s.step_name,
                    "order": s.order,
                    "completed": s.completed,
                    "description": s.description,
                }
                for s in self.guidance_steps
            ],
        }

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """
        执行自助服务任务
        task_type: 
          - identify_opportunities: AI落地机会识别
          - guide_requirement: 需求自助梳理引导
          - configure_solution: 方案自助配置
          - generate_prototype: 原型生成
          - calculate_value: 价值计算
          - detect_deviation: 纠偏检测
          - submit_feedback: 提交反馈
        """
        start = time.time()
        task_type = input_data.get("task_type", "identify_opportunities")

        try:
            if task_type == "identify_opportunities":
                result = await self._identify_opportunities(input_data)
            elif task_type == "guide_requirement":
                result = await self._guide_requirement(input_data)
            elif task_type == "configure_solution":
                result = await self._configure_solution(input_data)
            elif task_type == "generate_prototype":
                result = await self._generate_prototype(input_data)
            elif task_type == "calculate_value":
                result = await self._calculate_value(input_data)
            elif task_type == "detect_deviation":
                result = await self._detect_deviation_task(input_data)
            elif task_type == "submit_feedback":
                result = await self._submit_feedback(input_data)
            elif task_type == "complete_step":
                result = await self._complete_step(input_data)
            elif task_type == "push_training":
                result = await self._push_training(input_data)
            elif task_type == "assess_maturity":
                result = await self._assess_maturity(input_data)
            elif task_type == "generate_quote":
                result = await self._generate_quote(input_data)
            elif task_type == "log_communication":
                result = await self._log_communication(input_data)
            else:
                result = AgentResult(
                    success=False,
                    error=f"未知的任务类型: {task_type}",
                    duration_seconds=time.time() - start,
                )

            result.duration_seconds = time.time() - start
            return result

        except Exception as e:
            return AgentResult(
                success=False,
                error=str(e),
                duration_seconds=time.time() - start,
            )

    async def _identify_opportunities(self, input_data: dict[str, Any]) -> AgentResult:
        """AI落地机会识别：通过对话引导客户梳理业务痛点，识别AI机会"""
        business_description = input_data.get("business_description", "")
        industry = input_data.get("industry", "")
        pain_points = input_data.get("pain_points", [])

        # Mock模式：基于业务描述生成AI落地机会
        opportunities = self._mock_identify_opportunities(
            business_description, industry, pain_points
        )

        self.opportunities = opportunities

        # 检测是否需要FDE介入（机会数量过多/过少/描述模糊）
        needs_review = len(opportunities) == 0 or len(opportunities) > 5

        return AgentResult(
            success=True,
            content=f"识别出{len(opportunities)}个AI落地机会",
            structured_output={
                "opportunities": [self._opportunity_to_dict(o) for o in opportunities],
                "recommended_opportunity": self._opportunity_to_dict(opportunities[0]) if opportunities else None,
                "needs_fde_review": needs_review,
                "next_step": "请选择1-2个机会深入分析，或联系FDE工程师获取专业建议",
            },
            metadata={"opportunity_count": len(opportunities)},
        )

    def _mock_identify_opportunities(
        self, business_description: str, industry: str, pain_points: list[str]
    ) -> list[AIOpportunity]:
        """Mock：基于业务描述生成AI落地机会"""
        templates = [
            {
                "title": "智能客服问答系统",
                "description": "基于业务文档构建知识库，实现常见问题自动回答，降低人工客服成本",
                "business_scenario": "客户咨询/售后服务",
                "ai_approach": "RAG知识库 + 大模型问答",
                "efficiency_gain": 60.0,
                "cost_saving": 150000.0,
                "difficulty": "low",
                "priority": "high",
                "roi": 8.5,
            },
            {
                "title": "业务文档智能审核",
                "description": "自动审核客户提交的业务资料完整性和合规性，识别缺失项和风险",
                "business_scenario": "资料审核/合规检查",
                "ai_approach": "文档解析 + 规则引擎 + LLM审核",
                "efficiency_gain": 70.0,
                "cost_saving": 80000.0,
                "difficulty": "medium",
                "priority": "high",
                "roi": 7.2,
            },
            {
                "title": "业务流程自动化助手",
                "description": "基于业务规则和历史案例，为业务处理提供智能建议，提升处理效率",
                "business_scenario": "业务处理/决策支持",
                "ai_approach": "知识图谱 + 案例推理 + LLM建议",
                "efficiency_gain": 40.0,
                "cost_saving": 120000.0,
                "difficulty": "medium",
                "priority": "medium",
                "roi": 6.8,
            },
            {
                "title": "数据报表自动生成",
                "description": "自动从业务系统提取数据，生成分析报表和可视化看板",
                "business_scenario": "数据分析/报表生成",
                "ai_approach": "数据抽取 + LLM分析 + 可视化生成",
                "efficiency_gain": 80.0,
                "cost_saving": 60000.0,
                "difficulty": "low",
                "priority": "medium",
                "roi": 7.5,
            },
            {
                "title": "智能培训助手",
                "description": "基于业务知识库，为新员工提供个性化培训和问答，缩短上手周期",
                "business_scenario": "员工培训/知识管理",
                "ai_approach": "知识库 + 个性化学习路径 + AI教练",
                "efficiency_gain": 50.0,
                "cost_saving": 100000.0,
                "difficulty": "medium",
                "priority": "low",
                "roi": 6.0,
            },
        ]

        opportunities = []
        for i, t in enumerate(templates[:3]):  # 默认返回3个机会
            opportunities.append(
                AIOpportunity(
                    opportunity_id=f"opp-{uuid.uuid4().hex[:8]}",
                    title=t["title"],
                    description=t["description"],
                    business_scenario=t["business_scenario"],
                    ai_approach=t["ai_approach"],
                    estimated_efficiency_gain=t["efficiency_gain"],
                    estimated_cost_saving=t["cost_saving"],
                    implementation_difficulty=t["difficulty"],
                    priority=t["priority"],
                    roi_score=t["roi"],
                )
            )
        return opportunities

    async def _guide_requirement(self, input_data: dict[str, Any]) -> AgentResult:
        """需求自助梳理引导：AI生成需求初稿，客户通过确认/修改/补充完成"""
        action = input_data.get("action", "generate_draft")
        requirement_draft = input_data.get("requirement_draft", {})
        user_feedback = input_data.get("user_feedback", "")

        if action == "generate_draft":
            # 生成需求初稿
            draft = self._mock_generate_requirement_draft(input_data)
            return AgentResult(
                success=True,
                content="已生成需求初稿，请确认、修改或补充",
                structured_output={
                    "requirement_draft": draft,
                    "guidance": "请逐项审核需求：1)确认正确的项 2)修改不准确的项 3)补充遗漏的项",
                    "actions_available": ["confirm", "modify", "add", "request_fde_help"],
                },
            )
        elif action == "confirm":
            # 客户确认需求
            step = self._get_step("requirement")
            if step:
                step.completed = True
                step.user_input = {"confirmed": True, "feedback": user_feedback}
            return AgentResult(
                success=True,
                content="需求基线已确认",
                structured_output={
                    "requirement_baseline": requirement_draft,
                    "baseline_version": "v1.0",
                    "confirmed": True,
                    "next_step": "进入方案配置阶段",
                },
            )
        elif action == "modify":
            # 客户修改需求
            modified = input_data.get("modified_requirements", {})
            return AgentResult(
                success=True,
                content="需求已更新，请继续审核",
                structured_output={
                    "requirement_draft": {**requirement_draft, **modified},
                    "modified_items": list(modified.keys()),
                },
            )
        elif action == "add":
            # 客户补充需求
            new_items = input_data.get("new_requirements", [])
            return AgentResult(
                success=True,
                content="已补充新需求",
                structured_output={
                    "added_items": new_items,
                    "total_items": len(requirement_draft.get("requirements", [])) + len(new_items),
                },
            )
        else:
            return AgentResult(success=False, error=f"未知的操作: {action}")

    def _mock_generate_requirement_draft(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Mock生成需求初稿"""
        return {
            "summary": "基于业务资料分析，识别出核心业务流程与AI落地机会",
            "requirements": [
                {
                    "id": "R1",
                    "title": "智能资料审核",
                    "description": "自动审核客户提交资料的完整性与合规性",
                    "priority": "P0",
                    "acceptance_criteria": "资料完整性识别准确率≥85%",
                },
                {
                    "id": "R2",
                    "title": "业务处理助手",
                    "description": "基于业务规则提供智能处理建议",
                    "priority": "P0",
                    "acceptance_criteria": "建议采纳率≥70%",
                },
                {
                    "id": "R3",
                    "title": "知识库问答",
                    "description": "基于业务文档构建知识库，支持自然语言问答",
                    "priority": "P1",
                    "acceptance_criteria": "问答准确率≥80%",
                },
            ],
            "mvp_scope": ["R1", "R2"],
            "estimated_effort": "10人天",
        }

    async def _configure_solution(self, input_data: dict[str, Any]) -> AgentResult:
        """方案自助配置：配置向导，客户选择功能模块"""
        selected_modules = input_data.get("selected_modules", [])
        deployment_mode = input_data.get("deployment_mode", "saas")
        integration_level = input_data.get("integration_level", "basic")

        # Mock：基于选择生成方案和成本估算
        solution = self._mock_generate_solution(selected_modules, deployment_mode, integration_level)

        return AgentResult(
            success=True,
            content="方案配置完成",
            structured_output={
                "solution": solution,
                "selected_modules": selected_modules,
                "cost_estimate": solution["cost_estimate"],
                "next_step": "确认方案后生成可试用原型",
            },
        )

    def _mock_generate_solution(
        self, modules: list[str], deployment: str, integration: str
    ) -> dict[str, Any]:
        """Mock生成方案"""
        base_cost = 50000 if deployment == "saas" else 150000
        module_cost = len(modules) * 20000
        integration_cost = {"basic": 0, "standard": 30000, "deep": 80000}.get(integration, 0)
        total = base_cost + module_cost + integration_cost

        return {
            "architecture": f"{deployment}部署，{integration}集成",
            "modules": modules or ["智能资料审核", "知识库问答"],
            "tech_stack": ["FastAPI", "PostgreSQL", "Qdrant", "DeepSeek LLM"],
            "cost_estimate": {
                "development": total,
                "monthly_maintenance": total * 0.15,
                "annual_total": total * 1.15,
                "currency": "CNY",
            },
            "timeline": "4-6周",
            "risks": ["需求变更可能导致成本增加", "数据接入需要客户配合"],
        }

    async def _generate_prototype(self, input_data: dict[str, Any]) -> AgentResult:
        """原型即时生成：生成可试用的知识库问答原型"""
        prototype_type = input_data.get("prototype_type", "knowledge_base_qa")
        config = input_data.get("config") or {}

        # Mock：生成原型配置和访问入口
        prototype = {
            "prototype_id": f"proto-{uuid.uuid4().hex[:8]}",
            "type": prototype_type,
            "name": config.get("name", "AI原型演示"),
            "status": "ready",
            "access_url": f"/prototypes/{uuid.uuid4().hex[:8]}/chat",
            "features": ["自然语言问答", "来源追溯", "反馈收集", "使用统计"],
            "limitations": ["仅使用测试数据", "不支持生产环境集成", "试用期14天"],
            "setup_time_seconds": 5.2,
        }

        return AgentResult(
            success=True,
            content=f"原型已生成：{prototype['name']}",
            structured_output={
                "prototype": prototype,
                "next_step": "点击访问链接开始试用，或提交反馈进行优化",
            },
        )

    async def _calculate_value(self, input_data: dict[str, Any]) -> AgentResult:
        """价值计算：计算AI落地带来的价值指标"""
        baseline = input_data.get("baseline") or {}
        current = input_data.get("current") or {}

        metrics = self._mock_calculate_value(baseline, current)
        self.value_metrics = metrics

        total_value = sum(m.improvement_percentage for m in metrics) / len(metrics) if metrics else 0

        return AgentResult(
            success=True,
            content=f"价值计算完成，平均提升{total_value:.1f}%",
            structured_output={
                "metrics": [self._metric_to_dict(m) for m in metrics],
                "summary": {
                    "average_improvement": total_value,
                    "estimated_annual_saving": sum(m.target_value for m in metrics if m.category == "cost"),
                    "value_score": min(total_value / 10, 10),
                },
                "roi_calculation": {
                    "investment": input_data.get("investment", 100000),
                    "annual_return": sum(m.target_value for m in metrics if m.category == "cost") or 150000,
                    "payback_months": 8,
                    "roi_ratio": 1.5,
                },
            },
        )

    def _mock_calculate_value(self, baseline: dict, current: dict) -> list[ValueMetric]:
        """Mock计算价值指标"""
        return [
            ValueMetric(
                metric_id="m1",
                name="资料审核效率",
                category="efficiency",
                current_value=baseline.get("review_time", 30),
                target_value=current.get("review_time", 9),
                unit="分钟/份",
                improvement_percentage=70.0,
                description="AI自动审核将单份资料审核时间从30分钟缩短到9分钟",
            ),
            ValueMetric(
                metric_id="m2",
                name="人工客服成本",
                category="cost",
                current_value=baseline.get("cs_cost", 200000),
                target_value=current.get("cs_cost", 80000),
                unit="元/年",
                improvement_percentage=60.0,
                description="常见问题自动回答覆盖60%，减少人工客服成本",
            ),
            ValueMetric(
                metric_id="m3",
                name="回答准确率",
                category="quality",
                current_value=baseline.get("accuracy", 65),
                target_value=current.get("accuracy", 88),
                unit="%",
                improvement_percentage=35.4,
                description="基于知识库的精准问答，准确率从65%提升到88%",
            ),
            ValueMetric(
                metric_id="m4",
                name="客户满意度",
                category="satisfaction",
                current_value=baseline.get("satisfaction", 3.5),
                target_value=current.get("satisfaction", 4.3),
                unit="分(5分制)",
                improvement_percentage=22.9,
                description="响应速度提升和答案质量改善，客户满意度提升",
            ),
        ]

    async def _detect_deviation_task(self, input_data: dict[str, Any]) -> AgentResult:
        """纠偏检测任务：检测客户操作偏离"""
        user_action = input_data.get("user_action", {})
        context = input_data.get("context", {})

        alerts = self._detect_deviations({**user_action, **context})

        return AgentResult(
            success=True,
            content=f"检测到{len(alerts)}个偏离提醒",
            structured_output={
                "alerts": alerts,
                "needs_immediate_attention": any(a["severity"] == "high" for a in alerts),
            },
        )

    def _detect_deviations(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """检测操作偏离最佳实践"""
        alerts = []

        # 检测1：需求描述过于模糊
        requirements = data.get("requirements", [])
        if requirements:
            vague_count = sum(1 for r in requirements if len(str(r.get("description", ""))) < 20)
            if vague_count > len(requirements) * 0.5:
                alerts.append({
                    "alert_id": f"dev-{uuid.uuid4().hex[:8]}",
                    "type": "vague_requirement",
                    "severity": "medium",
                    "message": "超过50%的需求描述过于模糊（少于20字），建议补充详细描述",
                    "suggestion": "为每个需求补充：具体功能、使用场景、验收标准",
                    "auto_fix_available": True,
                })

        # 检测2：选择了过多功能模块（MVP原则）
        selected_modules = data.get("selected_modules", [])
        if len(selected_modules) > 5:
            alerts.append({
                "alert_id": f"dev-{uuid.uuid4().hex[:8]}",
                "type": "scope_creep",
                "severity": "high",
                "message": f"选择了{len(selected_modules)}个功能模块，超出MVP建议范围（≤5个）",
                "suggestion": "建议优先选择3-5个核心功能，其他功能放入二期规划",
                "auto_fix_available": False,
                "needs_fde_review": True,
            })

        # 检测3：预算与功能不匹配
        budget = data.get("budget", 0)
        if budget and budget < 50000 and len(selected_modules) > 3:
            alerts.append({
                "alert_id": f"dev-{uuid.uuid4().hex[:8]}",
                "type": "budget_mismatch",
                "severity": "high",
                "message": f"预算{budget}元不足以支撑{len(selected_modules)}个功能模块",
                "suggestion": "建议减少功能模块或增加预算，或联系FDE获取性价比方案",
                "auto_fix_available": False,
                "needs_fde_review": True,
            })

        # 检测4：跳过关键步骤
        skipped_steps = data.get("skipped_steps", [])
        critical_steps = ["requirement", "solution"]
        skipped_critical = [s for s in skipped_steps if s in critical_steps]
        if skipped_critical:
            alerts.append({
                "alert_id": f"dev-{uuid.uuid4().hex[:8]}",
                "type": "skipped_critical_step",
                "severity": "high",
                "message": f"跳过了关键步骤：{', '.join(skipped_critical)}",
                "suggestion": "关键步骤不可跳过，建议返回完成",
                "auto_fix_available": False,
                "needs_fde_review": True,
            })

        return alerts

    async def _submit_feedback(self, input_data: dict[str, Any]) -> AgentResult:
        """提交反馈：客户试用反馈和问题"""
        feedback_type = input_data.get("feedback_type", "general")
        content = input_data.get("content", "")
        rating = input_data.get("rating", 0)
        prototype_id = input_data.get("prototype_id", "")

        feedback = {
            "feedback_id": f"fb-{uuid.uuid4().hex[:8]}",
            "type": feedback_type,
            "content": content,
            "rating": rating,
            "prototype_id": prototype_id,
            "status": "pending_review",
            "submitted_at": time.time(),
        }

        # 自动分类和优先级
        priority = "high" if rating and rating <= 2 or "bug" in feedback_type else "medium"

        return AgentResult(
            success=True,
            content="反馈已提交，FDE工程师会尽快处理",
            structured_output={
                "feedback": feedback,
                "priority": priority,
                "estimated_response_time": "24小时内",
                "next_step": "FDE工程师审核后会联系您，或自动修复后通知您",
            },
        )

    async def _complete_step(self, input_data: dict[str, Any]) -> AgentResult:
        """完成引导步骤"""
        step_id = input_data.get("step_id", "")
        user_confirmation = input_data.get("confirmation", False)

        step = self._get_step(step_id)
        if not step:
            return AgentResult(success=False, error=f"步骤不存在: {step_id}")

        if not user_confirmation:
            return AgentResult(
                success=False,
                error="需要用户确认才能完成步骤",
                structured_output={"needs_confirmation": True},
            )

        step.completed = True
        step.user_input = input_data.get("user_input", {})
        next_step = self.get_current_step()

        return AgentResult(
            success=True,
            content=f"步骤[{step.step_name}]已完成",
            structured_output={
                "completed_step": step.step_id,
                "next_step": next_step.step_id if next_step else None,
                "next_step_name": next_step.step_name if next_step else None,
                "progress": self.get_guidance_progress(),
                "all_completed": next_step is None,
            },
        )

    def _complete_step_sync(self, step_id: str, confirmation: bool = False, user_input: Optional[dict] = None) -> AgentResult:
        """同步包装：完成引导步骤（供测试和同步调用场景使用）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 已有运行中的事件循环，直接调用内部逻辑
                return self._complete_step_internal(step_id, confirmation, user_input)
        except RuntimeError:
            pass
        return asyncio.run(self._complete_step({
            "step_id": step_id,
            "confirmation": confirmation,
            "user_input": user_input or {},
        }))

    def _complete_step_internal(self, step_id: str, confirmation: bool, user_input: Optional[dict]) -> AgentResult:
        """完成引导步骤的内部逻辑（同步版本）"""
        step = self._get_step(step_id)
        if not step:
            return AgentResult(success=False, error=f"步骤不存在: {step_id}")
        if not confirmation:
            return AgentResult(
                success=False,
                error="需要用户确认才能完成步骤",
                structured_output={"needs_confirmation": True},
            )
        step.completed = True
        step.user_input = user_input or {}
        next_step = self.get_current_step()
        return AgentResult(
            success=True,
            content=f"步骤[{step.step_name}]已完成",
            structured_output={
                "completed_step": step.step_id,
                "next_step": next_step.step_id if next_step else None,
                "next_step_name": next_step.step_name if next_step else None,
                "progress": self.get_guidance_progress(),
                "all_completed": next_step is None,
            },
        )

    def _get_step(self, step_id: str) -> Optional[GuidanceStep]:
        for s in self.guidance_steps:
            if s.step_id == step_id:
                return s
        return None

    def _update_value_metrics(self, data: dict[str, Any]):
        """更新价值指标"""
        if "metrics" in data:
            for m in data["metrics"]:
                existing = next((v for v in self.value_metrics if v.metric_id == m.get("metric_id")), None)
                if existing:
                    existing.current_value = m.get("current_value", existing.current_value)
                    existing.target_value = m.get("target_value", existing.target_value)

    def _opportunity_to_dict(self, opp: AIOpportunity) -> dict[str, Any]:
        return {
            "opportunity_id": opp.opportunity_id,
            "title": opp.title,
            "description": opp.description,
            "business_scenario": opp.business_scenario,
            "ai_approach": opp.ai_approach,
            "estimated_efficiency_gain": opp.estimated_efficiency_gain,
            "estimated_cost_saving": opp.estimated_cost_saving,
            "implementation_difficulty": opp.implementation_difficulty,
            "priority": opp.priority,
            "roi_score": opp.roi_score,
        }

    def _metric_to_dict(self, m: ValueMetric) -> dict[str, Any]:
        return {
            "metric_id": m.metric_id,
            "name": m.name,
            "category": m.category,
            "current_value": m.current_value,
            "target_value": m.target_value,
            "unit": m.unit,
            "improvement_percentage": m.improvement_percentage,
            "description": m.description,
        }

    # ================================================================
    # F7 P1 增强功能
    # ================================================================

    async def _push_training(self, input_data: dict[str, Any]) -> AgentResult:
        """F7.10 培训内容推送：基于客户当前阶段和能力短板推送相关培训内容"""
        current_step = self.get_current_step()
        step_id = current_step.step_id if current_step else "completed"
        customer_level = input_data.get("customer_level", "L1")

        # 基于当前阶段和客户等级生成培训内容
        training_contents = self._mock_get_training_content(step_id, customer_level)

        return AgentResult(
            success=True,
            content=f"已推送{len(training_contents)}条培训内容",
            structured_output={
                "current_stage": step_id,
                "customer_level": customer_level,
                "training_contents": training_contents,
                "push_strategy": "基于当前阶段+能力短板+历史行为的个性化推送",
            },
        )

    def _mock_get_training_content(self, stage: str, level: str) -> list[dict[str, Any]]:
        """Mock：基于阶段和等级生成培训内容"""
        content_map = {
            "enlightenment": [
                {"id": "t1", "title": "AI能做什么：3分钟了解AI应用场景", "type": "video", "duration_min": 3, "level": "L1"},
                {"id": "t2", "title": "如何描述你的业务痛点（模板+示例）", "type": "article", "duration_min": 5, "level": "L1"},
                {"id": "t3", "title": "ROI怎么算：AI项目投资回报快速评估", "type": "interactive", "duration_min": 8, "level": "L2"},
            ],
            "requirement": [
                {"id": "t4", "title": "需求梳理方法论：从业务描述到可执行需求", "type": "video", "duration_min": 10, "level": "L2"},
                {"id": "t5", "title": "如何写好验收标准（SMART原则+示例）", "type": "article", "duration_min": 6, "level": "L2"},
                {"id": "t6", "title": "MVP原则：第一期做什么不做什么", "type": "interactive", "duration_min": 12, "level": "L3"},
            ],
            "solution": [
                {"id": "t7", "title": "技术方案怎么看：非技术人员的方案评审指南", "type": "video", "duration_min": 15, "level": "L2"},
                {"id": "t8", "title": "SaaS vs 私有化部署：如何选择", "type": "article", "duration_min": 8, "level": "L3"},
                {"id": "t9", "title": "成本构成详解：开发费+维护费+隐藏成本", "type": "interactive", "duration_min": 10, "level": "L3"},
            ],
            "prototype": [
                {"id": "t10", "title": "原型试用指南：怎么试才能发现真问题", "type": "video", "duration_min": 8, "level": "L2"},
                {"id": "t11", "title": "如何写有效的反馈（模板+反例）", "type": "article", "duration_min": 5, "level": "L2"},
            ],
            "decision": [
                {"id": "t12", "title": "AI项目决策清单：上线前必须确认的10件事", "type": "checklist", "duration_min": 10, "level": "L3"},
                {"id": "t13", "title": "合同与SLA：AI项目合同关键条款解读", "type": "article", "duration_min": 12, "level": "L4"},
            ],
            "completed": [
                {"id": "t14", "title": "AI项目运营手册：上线后持续优化指南", "type": "guide", "duration_min": 20, "level": "L3"},
                {"id": "t15", "title": "进阶：如何在企业内部推广AI应用", "type": "video", "duration_min": 15, "level": "L4"},
            ],
        }
        contents = content_map.get(stage, content_map["enlightenment"])
        # 过滤等级匹配的内容
        level_order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
        filtered = [c for c in contents if level_order.get(c["level"], 1) <= level_order.get(level, 2) + 1]
        return filtered or contents

    async def _assess_maturity(self, input_data: dict[str, Any]) -> AgentResult:
        """F7.11 客户成长路径：评估客户AI能力成熟度（L1-L4）"""
        # 基于客户行为数据评估成熟度
        behavior = input_data.get("behavior", {})
        assessment = self._mock_assess_maturity(behavior)

        return AgentResult(
            success=True,
            content=f"客户AI能力成熟度评估：{assessment['level']} {assessment['level_name']}",
            structured_output={
                "assessment": assessment,
                "dimensions": assessment["dimensions"],
                "next_level_recommendations": assessment["next_level_recommendations"],
                "growth_path": assessment["growth_path"],
            },
        )

    def _mock_assess_maturity(self, behavior: dict) -> dict[str, Any]:
        """Mock：评估客户AI能力成熟度"""
        # 四个维度评分（0-100）
        dimensions = {
            "ai_cognition": behavior.get("ai_cognition_score", 35),  # AI认知
            "requirement_clarity": behavior.get("requirement_score", 45),  # 需求清晰度
            "tech_understanding": behavior.get("tech_score", 25),  # 技术理解
            "self_service_ability": behavior.get("self_service_score", 30),  # 自助能力
        }
        avg_score = sum(dimensions.values()) / len(dimensions)

        # 确定等级
        if avg_score < 30:
            level, level_name = "L1", "入门级"
        elif avg_score < 55:
            level, level_name = "L2", "进阶级"
        elif avg_score < 80:
            level, level_name = "L3", "精通级"
        else:
            level, level_name = "L4", "专家级"

        next_level_map = {
            "L1": ("L2", "进阶级", ["完成1个完整自助项目", "能独立描述业务需求", "理解AI基本概念"]),
            "L2": ("L3", "精通级", ["能独立评审技术方案", "理解ROI和成本构成", "能指导内部团队使用AI"]),
            "L3": ("L4", "专家级", ["能独立设计AI落地方案", "能培训他人", "能参与AI项目商业决策"]),
            "L4": (None, None, ["已达最高等级，可成为AI应用推广大使"]),
        }
        next_level, next_name, recommendations = next_level_map[level]

        return {
            "level": level,
            "level_name": level_name,
            "avg_score": round(avg_score, 1),
            "dimensions": dimensions,
            "next_level": next_level,
            "next_level_name": next_name,
            "next_level_recommendations": recommendations,
            "growth_path": [
                {"level": "L1", "name": "入门级", "achieved": level in ["L1", "L2", "L3", "L4"]},
                {"level": "L2", "name": "进阶级", "achieved": level in ["L2", "L3", "L4"]},
                {"level": "L3", "name": "精通级", "achieved": level in ["L3", "L4"]},
                {"level": "L4", "name": "专家级", "achieved": level == "L4"},
            ],
        }

    async def _generate_quote(self, input_data: dict[str, Any]) -> AgentResult:
        """F7.12 付费转化引导：基于项目价值和进度生成分阶段报价和转化建议"""
        project_value = input_data.get("project_value", {})
        current_stage = input_data.get("current_stage", "prototype")
        selected_modules = input_data.get("selected_modules", [])

        quote = self._mock_generate_quote(project_value, current_stage, selected_modules)

        return AgentResult(
            success=True,
            content=f"已生成报价方案，首年费用{quote['first_year_total']}元",
            structured_output={
                "quote": quote,
                "conversion_strategy": quote["conversion_strategy"],
                "next_best_action": quote["next_best_action"],
            },
        )

    def _mock_generate_quote(self, value: dict, stage: str, modules: list) -> dict[str, Any]:
        """Mock：生成分阶段报价"""
        module_count = max(len(modules), 2)
        base_dev = 50000 + module_count * 15000
        monthly_fee = base_dev * 0.15

        # 分阶段报价
        phased_pricing = [
            {
                "phase": "POC验证期",
                "duration": "2周",
                "price": 0,
                "description": "免费原型验证，确认价值后再付费",
                "deliverables": ["可试用原型", "价值评估报告", "技术可行性确认"],
            },
            {
                "phase": "MVP开发期",
                "duration": "4-6周",
                "price": base_dev,
                "description": "核心功能开发，上线可用版本",
                "deliverables": ["生产环境部署", "核心功能上线", "用户培训", "1个月免费维护"],
            },
            {
                "phase": "运营优化期",
                "duration": "持续",
                "price": monthly_fee,
                "price_unit": "月",
                "description": "持续优化、Badcase修复、功能迭代",
                "deliverables": ["7×24监控", "月度优化报告", "Badcase快速修复", "新功能迭代"],
            },
        ]

        first_year_total = base_dev + monthly_fee * 6  # 首年：开发费+6个月维护

        # 转化策略
        if stage == "prototype":
            conversion_strategy = "客户正在试用原型，重点展示价值数据，推动MVP签约"
            next_action = "安排价值复盘会议，用ROI数据说服决策层"
        elif stage == "decision":
            conversion_strategy = "客户已进入决策阶段，提供限时优惠和分阶段付款方案"
            next_action = "发送正式报价单和合同，提供首月免费维护优惠"
        else:
            conversion_strategy = "持续培育，推送成功案例和价值内容"
            next_action = "邀请参加AI落地分享会，建立信任"

        return {
            "phased_pricing": phased_pricing,
            "first_year_total": first_year_total,
            "monthly_maintenance": monthly_fee,
            "roi_payback_months": 8,
            "conversion_strategy": conversion_strategy,
            "next_best_action": next_action,
            "discount_available": stage in ["prototype", "decision"],
            "discount_details": "限时优惠：签约即送2个月免费维护（价值{:.0f}元）".format(monthly_fee * 2),
        }

    async def _log_communication(self, input_data: dict[str, Any]) -> AgentResult:
        """F7.13 客户沟通通道：记录沟通历史，生成沟通摘要和下一步建议"""
        comm_type = input_data.get("type", "meeting")  # meeting/email/chat/call
        content = input_data.get("content", "")
        participants = input_data.get("participants", [])

        # Mock：生成沟通摘要和行动项
        summary = self._mock_generate_communication_summary(comm_type, content)

        return AgentResult(
            success=True,
            content=f"沟通记录已保存，生成{len(summary['action_items'])}个行动项",
            structured_output={
                "communication_id": f"comm-{uuid.uuid4().hex[:8]}",
                "type": comm_type,
                "summary": summary,
                "participants": participants,
                "next_fde_action": summary["next_fde_action"],
            },
        )

    def _mock_generate_communication_summary(self, comm_type: str, content: str) -> dict[str, Any]:
        """Mock：生成沟通摘要"""
        return {
            "key_points": [
                "客户对原型的问答准确率表示满意",
                "客户希望增加数据导出功能",
                "客户关注数据安全和私有化部署选项",
                "客户计划在下个月内部决策会议上汇报",
            ],
            "action_items": [
                {"id": "a1", "item": "评估数据导出功能的开发工作量", "owner": "FDE工程师", "due": "3天内", "priority": "high"},
                {"id": "a2", "item": "准备私有化部署方案和报价", "owner": "FDE工程师", "due": "1周内", "priority": "medium"},
                {"id": "a3", "item": "准备客户内部汇报材料（价值+案例）", "owner": "AI落地合伙人", "due": "1周内", "priority": "high"},
            ],
            "concerns": ["数据安全", "部署方式", "决策时间线"],
            "next_fde_action": "3天内提供数据导出功能评估和私有化部署方案，1周内准备汇报材料",
            "sentiment": "positive",
            "conversion_likelihood": "high",
        }
