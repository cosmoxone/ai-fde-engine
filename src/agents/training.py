"""
FDE培训成长Agent - F8模块
核心能力：能力模型定义、个性化学习路径生成、AI教练对话辅导、实战演练沙箱、
         实时操作反馈、知识库与案例库、能力评估与认证
设计理念：AI主导的FDE快速成长体系，6周从零基础到合格FDE
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .base import BaseAgent, AgentResult, AgentCapability


@dataclass
class CompetencyScore:
    """能力项评分"""
    competency_id: str
    name: str
    dimension: str  # knowledge/skill/experience
    level: int  # 0-5
    score: float  # 0-100
    evidence: str = ""
    last_assessed: float = 0.0


@dataclass
class LearningPath:
    """学习路径"""
    path_id: str
    learner_id: str
    target_level: str  # L1-L5
    duration_weeks: int
    modules: list[dict]
    current_week: int = 1
    progress_percentage: float = 0.0


@dataclass
class TrainingCase:
    """培训案例"""
    case_id: str
    title: str
    category: str  # ai_tech/business_analysis/solution_design/engineering/customer_communication
    difficulty: str  # beginner/intermediate/advanced
    content: str
    tags: list[str] = field(default_factory=list)


class TrainingAgent(BaseAgent):
    """
    FDE培训成长Agent
    服务对象：FDE工程师（新手培养+持续提升）
    工作方式：AI教练7×24陪伴 + 实战项目驱动 + 实时反馈纠偏 + 能力量化评估
    """

    agent_type = "training"
    agent_name = "FDE培训成长Agent"
    description = "AI主导的FDE工程师快速成长体系"

    # FDE能力模型定义（三维度×多能力项）
    COMPETENCY_MODEL = {
        "knowledge": {
            "name": "知识维度 (Know-what)",
            "competencies": [
                {"id": "k1", "name": "AI技术基础", "description": "大模型/Agent/RAG/评测/微调"},
                {"id": "k2", "name": "业务分析知识", "description": "流程建模/需求分析/数据梳理"},
                {"id": "k3", "name": "工程技术知识", "description": "后端开发/API设计/部署运维"},
                {"id": "k4", "name": "行业知识", "description": "目标行业业务场景和术语"},
                {"id": "k5", "name": "项目管理知识", "description": "敏捷/风险管理/质量保障"},
            ],
        },
        "skill": {
            "name": "技能维度 (Know-how)",
            "competencies": [
                {"id": "s1", "name": "需求分析能力", "description": "从业务描述到可执行需求"},
                {"id": "s2", "name": "方案设计能力", "description": "产品方案/技术方案/验证方案"},
                {"id": "s3", "name": "AI应用开发能力", "description": "Prompt工程/Agent开发/RAG构建"},
                {"id": "s4", "name": "问题排查能力", "description": "Badcase分析/故障定位/性能优化"},
                {"id": "s5", "name": "客户沟通能力", "description": "需求确认/方案汇报/异议处理"},
                {"id": "s6", "name": "项目管理能力", "description": "进度管控/风险识别/期望管理"},
            ],
        },
        "experience": {
            "name": "经验维度 (Know-why)",
            "competencies": [
                {"id": "e1", "name": "项目交付经验", "description": "完整项目交付数量和复杂度"},
                {"id": "e2", "name": "行业场景经验", "description": "特定行业的AI落地经验"},
                {"id": "e3", "name": "踩坑复盘经验", "description": "问题处理和复盘沉淀"},
                {"id": "e4", "name": "最佳实践沉淀", "description": "方法论和模板的贡献"},
            ],
        },
    }

    # 等级定义
    LEVELS = {
        "L1": {"name": "见习FDE", "min_score": 0, "max_score": 20, "can_independent": False, "training_weeks": "0-2周"},
        "L2": {"name": "初级FDE", "min_score": 20, "max_score": 40, "can_independent": "简单项目(需导师Review)", "training_weeks": "2-4周"},
        "L3": {"name": "合格FDE", "min_score": 40, "max_score": 65, "can_independent": "标准项目", "training_weeks": "4-6周"},
        "L4": {"name": "高级FDE", "min_score": 65, "max_score": 85, "can_independent": "复杂项目+带新人", "training_weeks": "3-6个月"},
        "L5": {"name": "专家FDE", "min_score": 85, "max_score": 100, "can_independent": "战略级项目+体系建设", "training_weeks": "6个月以上"},
    }

    def __init__(self, project_id: str, learner_id: Optional[str] = None, **kwargs):
        super().__init__(project_id, model_task="research", **kwargs)
        self.learner_id = learner_id or f"learner-{uuid.uuid4().hex[:8]}"
        self.competency_scores: list[CompetencyScore] = []
        self.learning_path: Optional[LearningPath] = None
        self.coach_conversations: list[dict] = []
        self.sandbox_projects: list[dict] = []
        self.certifications: list[dict] = []
        self._init_competency_scores()

    def get_system_prompt(self) -> str:
        return """你是一位资深的FDE培训教练，负责培养AI落地工程师。

你的核心职责：
1. 能力评估：基于FDE三维能力模型（知识/技能/经验）评估学员当前水平
2. 学习路径：为学员生成个性化的6周成长计划
3. AI教练：7×24小时解答技术问题、指导方案设计、审核代码质量
4. 实战演练：在沙箱环境中引导学员完成完整交付流程
5. 实时反馈：学员操作时即时点评，纠正错误，推荐最佳实践
6. 认证考核：阶段性评估，通过后颁发等级认证

教学原则：
- 实战驱动：在做中学，每个知识点都配套实战任务
- 即时反馈：操作即时点评，错误即时纠正
- 个性化：根据学员背景和短板调整学习内容
- 量化评估：用数据说话，能力提升可衡量
- 循序渐进：从L1到L5，每级有明确的能力标准
"""

    def _init_competency_scores(self):
        """初始化能力评分（默认L1水平）"""
        for dim, dim_data in self.COMPETENCY_MODEL.items():
            for comp in dim_data["competencies"]:
                self.competency_scores.append(CompetencyScore(
                    competency_id=comp["id"],
                    name=comp["name"],
                    dimension=dim,
                    level=1,
                    score=15.0,
                    last_assessed=time.time(),
                ))

    def _default_capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="coach_mode",
                description="教练模式：苏格拉底式提问引导，而非直接给答案",
            ),
            AgentCapability(
                name="real_time_feedback",
                description="实时反馈：学员操作即时点评",
            ),
        ]

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """
        执行培训任务
        task_type:
          - get_competency_model: 获取能力模型定义
          - assess_competency: 能力评估
          - generate_learning_path: 生成学习路径
          - coach_chat: AI教练对话
          - start_sandbox: 启动实战沙箱
          - submit_sandbox_work: 提交沙箱作业
          - get_feedback: 获取操作反馈
          - search_knowledge: 搜索知识库
          - get_certification: 获取认证
          - take_exam: 参加考核
        """
        start = time.time()
        task_type = input_data.get("task_type", "get_competency_model")

        try:
            if task_type == "get_competency_model":
                result = self._get_competency_model()
            elif task_type == "assess_competency":
                result = await self._assess_competency(input_data)
            elif task_type == "generate_learning_path":
                result = await self._generate_learning_path(input_data)
            elif task_type == "coach_chat":
                result = await self._coach_chat(input_data)
            elif task_type == "start_sandbox":
                result = await self._start_sandbox(input_data)
            elif task_type == "submit_sandbox_work":
                result = await self._submit_sandbox_work(input_data)
            elif task_type == "get_feedback":
                result = self._get_feedback(input_data)
            elif task_type == "search_knowledge":
                result = self._search_knowledge(input_data)
            elif task_type == "take_exam":
                result = await self._take_exam(input_data)
            elif task_type == "get_certification":
                result = self._get_certification(input_data)
            else:
                result = AgentResult(success=False, error=f"未知任务类型: {task_type}")

            result.duration_seconds = time.time() - start
            return result
        except Exception as e:
            return AgentResult(success=False, error=str(e), duration_seconds=time.time() - start)

    def _get_competency_model(self) -> AgentResult:
        """F8.1 获取FDE能力模型定义"""
        return AgentResult(
            success=True,
            content="FDE三维能力模型（知识/技能/经验）× 五等级（L1-L5）",
            structured_output={
                "model": self.COMPETENCY_MODEL,
                "levels": self.LEVELS,
                "total_competencies": sum(len(d["competencies"]) for d in self.COMPETENCY_MODEL.values()),
                "learner_id": self.learner_id,
            },
        )

    async def _assess_competency(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.1+F8.7 能力评估：基于学员背景和表现评估能力水平"""
        background = input_data.get("background", {})
        assessment_data = input_data.get("assessment", {})

        # Mock：基于背景调整初始评分
        scores = self._mock_assess(background, assessment_data)
        self.competency_scores = scores

        # 计算综合等级
        avg_score = sum(s.score for s in scores) / len(scores)
        level = self._score_to_level(avg_score)

        return AgentResult(
            success=True,
            content=f"能力评估完成，综合等级：{level} {self.LEVELS[level]['name']}",
            structured_output={
                "learner_id": self.learner_id,
                "overall_level": level,
                "overall_level_name": self.LEVELS[level]["name"],
                "avg_score": round(avg_score, 1),
                "dimension_scores": self._get_dimension_scores(),
                "competency_scores": [self._score_to_dict(s) for s in scores],
                "strengths": self._get_strengths(scores),
                "weaknesses": self._get_weaknesses(scores),
                "can_independent": self.LEVELS[level]["can_independent"],
            },
        )

    def _mock_assess(self, background: dict, assessment: dict) -> list[CompetencyScore]:
        """Mock：基于背景评估能力"""
        base_bonus = 0
        if background.get("ai_experience_years", 0) > 0:
            base_bonus += background["ai_experience_years"] * 5
        if background.get("dev_experience_years", 0) > 0:
            base_bonus += background["dev_experience_years"] * 3
        if background.get("fde_experience", False):
            base_bonus += 15

        scores = []
        for s in self.competency_scores:
            bonus = base_bonus
            # 不同维度有不同的背景加成
            if s.dimension == "knowledge" and background.get("ai_experience_years", 0) > 0:
                bonus += 5
            if s.dimension == "skill" and background.get("dev_experience_years", 0) > 0:
                bonus += 8
            if s.dimension == "experience" and background.get("fde_experience", False):
                bonus += 10

            new_score = min(100, max(10, 15 + bonus + assessment.get(s.competency_id, 0)))
            s.score = round(new_score, 1)
            s.level = self._score_to_level_number(new_score)
            s.last_assessed = time.time()
            scores.append(s)
        return scores

    async def _generate_learning_path(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.2 生成个性化学习路径"""
        target_level = input_data.get("target_level", "L3")
        background = input_data.get("background", {})
        current_level = input_data.get("current_level", "L1")

        path = self._mock_generate_path(target_level, current_level, background)
        self.learning_path = path

        return AgentResult(
            success=True,
            content=f"学习路径已生成：{path.duration_weeks}周达到{target_level}",
            structured_output={
                "path": {
                    "path_id": path.path_id,
                    "learner_id": self.learner_id,
                    "target_level": target_level,
                    "duration_weeks": path.duration_weeks,
                    "current_week": path.current_week,
                    "progress_percentage": path.progress_percentage,
                },
                "weekly_plan": path.modules,
                "prerequisites": self._get_prerequisites(current_level, target_level),
                "estimated_effort_hours": path.duration_weeks * 20,
            },
        )

    def _mock_generate_path(self, target: str, current: str, background: dict) -> LearningPath:
        """Mock：生成6周学习路径"""
        weeks = [
            {
                "week": 1,
                "theme": "基础认知",
                "goal": "掌握AI基础概念和FDE方法论",
                "topics": ["大模型基础", "Agent架构", "RAG原理", "FDE工作方法论", "系统操作培训"],
                "practical_tasks": ["完成AI基础概念测试", "在沙箱中创建第一个项目", "通读FDE交付手册"],
                "assessment": "基础概念笔试 + 系统操作实操",
                "hours": 20,
            },
            {
                "week": 2,
                "theme": "调研分析实战",
                "goal": "能独立完成项目调研分析",
                "topics": ["文档解析技巧", "业务流程建模", "数据资产梳理", "Benchmark生成方法"],
                "practical_tasks": ["沙箱项目1：完成完整调研分析", "生成3个AI落地机会", "构建10条Benchmark用例"],
                "assessment": "独立完成一个项目的调研分析并通过导师Review",
                "hours": 25,
            },
            {
                "week": 3,
                "theme": "方案设计实战",
                "goal": "能独立完成三方案设计",
                "topics": ["产品方案设计", "技术方案选型", "验证方案设计", "方案交叉校验方法"],
                "practical_tasks": ["沙箱项目2：基于调研结果完成方案设计", "对比AI方案与人工方案差异", "完成方案成本估算"],
                "assessment": "独立完成三方案设计并通过审核",
                "hours": 25,
            },
            {
                "week": 4,
                "theme": "开发交付实战",
                "goal": "能独立完成代码生成和部署",
                "topics": ["Prompt工程进阶", "Agent开发实战", "知识库构建", "质量门禁使用", "Badcase处理"],
                "practical_tasks": ["沙箱项目3：完成代码生成", "构建知识库并测试问答", "处理5个模拟Badcase", "完成部署"],
                "assessment": "独立完成开发交付并通过质量门禁",
                "hours": 30,
            },
            {
                "week": 5,
                "theme": "客户沟通与项目管理",
                "goal": "能独立进行客户沟通和项目管控",
                "topics": ["需求确认技巧", "方案汇报方法", "异议处理", "风险识别", "客户期望管理"],
                "practical_tasks": ["AI模拟客户沟通演练（3轮）", "完成一次模拟方案汇报", "制定项目风险清单"],
                "assessment": "独立完成一次客户方案汇报（AI扮演客户评分）",
                "hours": 20,
            },
            {
                "week": 6,
                "theme": "综合实战与认证",
                "goal": "独立完成完整项目交付，通过L3认证",
                "topics": ["综合项目交付", "质量保障", "文档撰写", "验收流程"],
                "practical_tasks": ["综合沙箱项目：独立完成完整交付（调研→方案→开发→迭代→验收）", "撰写项目交付文档", "准备认证考核"],
                "assessment": "L3认证考核（理论+实操+案例分析）",
                "hours": 35,
            },
        ]
        return LearningPath(
            path_id=f"path-{uuid.uuid4().hex[:8]}",
            learner_id=self.learner_id,
            target_level=target,
            duration_weeks=6,
            modules=weeks,
        )

    async def _coach_chat(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.3 AI教练对话辅导"""
        message = input_data.get("message", "")
        context = input_data.get("context", {})
        conversation_id = input_data.get("conversation_id", f"conv-{uuid.uuid4().hex[:8]}")

        # Mock：AI教练回复
        reply = self._mock_coach_reply(message, context)

        self.coach_conversations.append({
            "conversation_id": conversation_id,
            "role": "user",
            "content": message,
            "timestamp": time.time(),
        })
        self.coach_conversations.append({
            "conversation_id": conversation_id,
            "role": "coach",
            "content": reply["answer"],
            "timestamp": time.time(),
        })

        return AgentResult(
            success=True,
            content=reply["answer"],
            structured_output={
                "conversation_id": conversation_id,
                "reply": reply,
                "related_resources": reply.get("resources", []),
                "suggested_next_steps": reply.get("next_steps", []),
            },
        )

    def _mock_coach_reply(self, message: str, context: dict) -> dict:
        """Mock：AI教练回复（苏格拉底式提问引导）"""
        msg_lower = message.lower()
        if any(k in msg_lower for k in ["怎么做", "如何", "how", "方法"]):
            return {
                "answer": f"关于「{message}」，让我们一起分析：\n\n1. 你目前的理解是什么？\n2. 你尝试过哪些方法？遇到了什么问题？\n3. 我建议你先从XX入手，因为...\n\n需要我提供具体的示例吗？",
                "resources": [{"title": "相关最佳实践", "type": "article", "url": "#"}],
                "next_steps": ["分享你目前的理解", "描述遇到的具体问题", "我会给出针对性建议"],
            }
        elif any(k in msg_lower for k in ["报错", "错误", "error", "bug", "失败"]):
            return {
                "answer": f"遇到问题了，让我们一起排查：\n\n1. 完整的错误信息是什么？\n2. 你在执行什么操作时遇到的？\n3. 最近做了什么改动？\n\n根据你描述的情况，可能的原因是XX。建议先检查XX配置。",
                "resources": [{"title": "常见问题排查指南", "type": "guide", "url": "#"}],
                "next_steps": ["提供完整错误日志", "描述复现步骤", "我会帮你定位根因"],
            }
        else:
            return {
                "answer": f"收到你的问题：「{message}」\n\n这是一个很好的问题。让我从几个角度来分析：\n\n1. 概念层面：...\n2. 实践层面：...\n3. 常见误区：...\n\n你想深入了解哪个方面？",
                "resources": [{"title": "FDE知识体系", "type": "knowledge_base", "url": "#"}],
                "next_steps": ["选择想深入的方向", "提出更具体的问题", "我会展开详细讲解"],
            }

    async def _start_sandbox(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.4 启动实战演练沙箱"""
        scenario = input_data.get("scenario", "full_delivery")
        difficulty = input_data.get("difficulty", "beginner")

        sandbox = {
            "sandbox_id": f"sb-{uuid.uuid4().hex[:8]}",
            "scenario": scenario,
            "difficulty": difficulty,
            "status": "ready",
            "project_name": f"沙箱演练-{scenario}",
            "tasks": self._mock_sandbox_tasks(scenario, difficulty),
            "time_limit_minutes": 120,
            "started_at": time.time(),
        }
        self.sandbox_projects.append(sandbox)

        return AgentResult(
            success=True,
            content=f"沙箱已启动：{sandbox['project_name']}",
            structured_output={
                "sandbox": sandbox,
                "guidance": "请按照任务列表逐步完成，每完成一个任务提交后我会即时点评",
                "ai_coach_available": True,
            },
        )

    def _mock_sandbox_tasks(self, scenario: str, difficulty: str) -> list[dict]:
        """Mock：生成沙箱任务列表"""
        task_sets = {
            "research": [
                {"id": "t1", "title": "上传业务资料并解析", "status": "pending", "points": 20},
                {"id": "t2", "title": "梳理业务流程图", "status": "pending", "points": 25},
                {"id": "t3", "title": "识别3个AI落地机会", "status": "pending", "points": 30},
                {"id": "t4", "title": "生成10条Benchmark用例", "status": "pending", "points": 25},
            ],
            "design": [
                {"id": "t1", "title": "基于需求基线生成产品方案", "status": "pending", "points": 30},
                {"id": "t2", "title": "生成技术方案（含架构图）", "status": "pending", "points": 30},
                {"id": "t3", "title": "生成验证方案", "status": "pending", "points": 20},
                {"id": "t4", "title": "方案交叉校验", "status": "pending", "points": 20},
            ],
            "full_delivery": [
                {"id": "t1", "title": "完成调研分析", "status": "pending", "points": 20},
                {"id": "t2", "title": "完成方案设计", "status": "pending", "points": 20},
                {"id": "t3", "title": "完成代码生成", "status": "pending", "points": 20},
                {"id": "t4", "title": "构建知识库", "status": "pending", "points": 15},
                {"id": "t5", "title": "通过质量门禁", "status": "pending", "points": 15},
                {"id": "t6", "title": "完成部署和验收", "status": "pending", "points": 10},
            ],
        }
        return task_sets.get(scenario, task_sets["full_delivery"])

    async def _submit_sandbox_work(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.4+F8.5 提交沙箱作业并获取即时反馈"""
        sandbox_id = input_data.get("sandbox_id", "")
        task_id = input_data.get("task_id", "")
        work_content = input_data.get("work", "")

        # Mock：AI点评作业
        feedback = self._mock_grade_work(task_id, work_content)

        return AgentResult(
            success=True,
            content=f"作业已提交，得分：{feedback['score']}/100",
            structured_output={
                "sandbox_id": sandbox_id,
                "task_id": task_id,
                "feedback": feedback,
                "passed": feedback["score"] >= 70,
                "next_task_suggestion": feedback.get("next_suggestion", ""),
            },
        )

    def _mock_grade_work(self, task_id: str, work: str) -> dict:
        """Mock：AI点评作业"""
        score = min(95, max(50, 60 + len(work) // 10))
        return {
            "score": score,
            "grade": "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D",
            "strengths": ["思路清晰", "覆盖了核心要点", "结构合理"],
            "improvements": ["可以补充更多具体示例", "部分细节可以更深入", "建议参考最佳实践模板"],
            "coach_comment": f"整体完成度不错，得分{score}。主要优点是思路清晰，覆盖了核心要点。建议在细节上更深入，补充具体示例。继续加油！",
            "next_suggestion": "建议继续下一个任务，或针对改进点重新提交",
        }

    def _get_feedback(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.5 获取操作反馈"""
        action = input_data.get("action", "")
        context = input_data.get("context", {})

        feedback = self._mock_action_feedback(action, context)

        return AgentResult(
            success=True,
            content=feedback["message"],
            structured_output={"feedback": feedback},
        )

    def _mock_action_feedback(self, action: str, context: dict) -> dict:
        """Mock：操作即时反馈"""
        feedback_map = {
            "create_project": {"severity": "info", "message": "项目创建成功！建议下一步：上传业务资料，启动调研分析", "best_practice": "项目名称应包含客户和场景，便于后续管理"},
            "upload_document": {"severity": "info", "message": "文档上传成功！AI正在解析，预计30秒内完成", "best_practice": "建议上传PDF/Word格式，扫描件建议先OCR处理"},
            "run_research": {"severity": "info", "message": "调研分析已启动！完成后会自动通知你审核", "best_practice": "调研前确保已上传足够的业务资料（至少3份）"},
            "generate_code": {"severity": "warning", "message": "代码生成中，注意：AI生成的代码必须经过人工Review才能上线", "best_practice": "代码生成后先运行测试，再进行人工Code Review"},
            "default": {"severity": "info", "message": "操作已完成", "best_practice": ""},
        }
        return feedback_map.get(action, feedback_map["default"])

    def _search_knowledge(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.6 搜索FDE知识库与案例库"""
        query = input_data.get("query", "")
        category = input_data.get("category", "all")

        results = self._mock_search_knowledge(query, category)

        return AgentResult(
            success=True,
            content=f"找到{len(results)}条相关知识",
            structured_output={"query": query, "results": results, "total": len(results)},
        )

    def _mock_search_knowledge(self, query: str, category: str) -> list[dict]:
        """Mock：搜索知识库"""
        knowledge_base = [
            {"id": "kb1", "title": "RAG知识库构建最佳实践", "category": "ai_tech", "difficulty": "intermediate", "summary": "从文档分块到Embedding选择，完整的RAG构建指南", "tags": ["RAG", "知识库", "Embedding"]},
            {"id": "kb2", "title": "Prompt工程进阶技巧", "category": "ai_tech", "difficulty": "advanced", "summary": "结构化Prompt、Few-shot、CoT等高级技巧", "tags": ["Prompt", "大模型", "技巧"]},
            {"id": "kb3", "title": "业务流程建模方法论", "category": "business_analysis", "difficulty": "beginner", "summary": "从访谈笔记到BPMN流程图的完整方法", "tags": ["流程建模", "需求分析", "BPMN"]},
            {"id": "kb4", "title": "AI项目方案设计模板", "category": "solution_design", "difficulty": "intermediate", "summary": "产品方案+技术方案+验证方案的标准模板和示例", "tags": ["方案设计", "模板", "最佳实践"]},
            {"id": "kb5", "title": "智能客服项目成功案例", "category": "case_study", "difficulty": "intermediate", "summary": "某电商平台智能客服项目从0到1的完整复盘", "tags": ["案例", "智能客服", "电商"]},
            {"id": "kb6", "title": "Badcase分析与修复指南", "category": "engineering", "difficulty": "intermediate", "summary": "常见Badcase类型、根因分析方法、修复策略", "tags": ["Badcase", "调试", "质量"]},
            {"id": "kb7", "title": "客户沟通：如何管理期望", "category": "customer_communication", "difficulty": "intermediate", "summary": "需求确认、方案汇报、异议处理的沟通技巧", "tags": ["沟通", "期望管理", "客户关系"]},
            {"id": "kb8", "title": "AI项目失败复盘Top10", "category": "case_study", "difficulty": "beginner", "summary": "从10个失败项目中总结的避坑指南", "tags": ["复盘", "失败案例", "避坑"]},
        ]
        # 简单过滤
        query_lower = query.lower()
        filtered = [k for k in knowledge_base if
                    (category == "all" or k["category"] == category) and
                    (not query or query_lower in k["title"].lower() or query_lower in k["summary"].lower() or any(query_lower in t.lower() for t in k["tags"]))]
        return filtered or knowledge_base[:3]

    async def _take_exam(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.7 参加能力考核"""
        target_level = input_data.get("target_level", "L3")
        answers = input_data.get("answers", {})

        # Mock：考核评分
        exam_result = self._mock_grade_exam(target_level, answers)

        if exam_result["passed"]:
            cert = {
                "cert_id": f"cert-{uuid.uuid4().hex[:8]}",
                "level": target_level,
                "level_name": self.LEVELS[target_level]["name"],
                "learner_id": self.learner_id,
                "issued_at": time.time(),
                "valid_until": time.time() + 365 * 24 * 3600,
                "score": exam_result["total_score"],
            }
            self.certifications.append(cert)
            exam_result["certification"] = cert

        return AgentResult(
            success=True,
            content=f"考核完成：{'通过' if exam_result['passed'] else '未通过'}，得分{exam_result['total_score']}",
            structured_output=exam_result,
        )

    def _mock_grade_exam(self, target_level: str, answers: dict) -> dict:
        """Mock：考核评分"""
        sections = [
            {"name": "理论知识", "score": 85, "total": 100, "passed": True},
            {"name": "实操能力", "score": 78, "total": 100, "passed": True},
            {"name": "案例分析", "score": 82, "total": 100, "passed": True},
        ]
        total = sum(s["score"] for s in sections) / len(sections)
        pass_threshold = {"L1": 50, "L2": 60, "L3": 70, "L4": 80, "L5": 90}.get(target_level, 70)
        passed = total >= pass_threshold

        return {
            "target_level": target_level,
            "total_score": round(total, 1),
            "pass_threshold": pass_threshold,
            "passed": passed,
            "sections": sections,
            "weak_areas": [s["name"] for s in sections if s["score"] < 80],
            "next_steps": ["针对薄弱环节加强学习", "1周后可重新考核"] if not passed else ["恭喜通过认证！", "可以开始独立承担项目"],
        }

    def _get_certification(self, input_data: dict[str, Any]) -> AgentResult:
        """F8.7 获取认证信息"""
        return AgentResult(
            success=True,
            content=f"已获得{len(self.certifications)}个认证",
            structured_output={
                "learner_id": self.learner_id,
                "certifications": self.certifications,
                "current_highest_level": max((c["level"] for c in self.certifications), default="L1"),
            },
        )

    # ===== 辅助方法 =====

    def _score_to_level(self, score: float) -> str:
        """分数转等级"""
        for level, data in self.LEVELS.items():
            if data["min_score"] <= score < data["max_score"]:
                return level
        return "L5"

    def _score_to_level_number(self, score: float) -> int:
        """分数转等级数字"""
        level = self._score_to_level(score)
        return int(level[1])

    def _get_dimension_scores(self) -> dict[str, Any]:
        """获取各维度平均分"""
        result = {}
        for dim, dim_data in self.COMPETENCY_MODEL.items():
            dim_scores = [s.score for s in self.competency_scores if s.dimension == dim]
            result[dim] = {
                "name": dim_data["name"],
                "avg_score": round(sum(dim_scores) / len(dim_scores), 1) if dim_scores else 0,
                "competency_count": len(dim_scores),
            }
        return result

    def _get_strengths(self, scores: list[CompetencyScore]) -> list[str]:
        """获取优势项"""
        sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
        return [f"{s.name}（{s.score}分）" for s in sorted_scores[:3]]

    def _get_weaknesses(self, scores: list[CompetencyScore]) -> list[str]:
        """获取薄弱项"""
        sorted_scores = sorted(scores, key=lambda s: s.score)
        return [f"{s.name}（{s.score}分）" for s in sorted_scores[:3]]

    def _get_prerequisites(self, current: str, target: str) -> list[str]:
        """获取前置要求"""
        prereqs = {
            ("L1", "L3"): ["AI基础概念", "编程基础", "了解业务分析基本方法"],
            ("L2", "L3"): ["完成L2认证", "有1个以上项目参与经验", "掌握基本的需求分析方法"],
            ("L3", "L4"): ["获得L3认证", "独立完成3个以上项目", "有带新人经验"],
        }
        return prereqs.get((current, target), ["完成当前等级认证", "有相关项目经验"])

    def _score_to_dict(self, s: CompetencyScore) -> dict[str, Any]:
        return {
            "competency_id": s.competency_id,
            "name": s.name,
            "dimension": s.dimension,
            "level": s.level,
            "score": s.score,
            "evidence": s.evidence,
        }
