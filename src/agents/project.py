"""
项目管控Agent - 负责进度跟踪、风险预警、文档生成、资产沉淀
模型：Qwen3.6系列
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import AgentResult, BaseAgent


class ProjectAgent(BaseAgent):
    """项目管控Agent：进度跟踪、风险预警、文档自动生成、资产沉淀"""

    agent_type = "project"
    agent_name = "项目管控Agent"
    description = "负责项目进度跟踪、风险预警、文档生成、资产沉淀与多项目管理"

    def __init__(self, project_id: str, **kwargs):
        kwargs.setdefault("model_task", "project")
        super().__init__(project_id, **kwargs)

    def get_system_prompt(self) -> str:
        return """你是一位资深的AI项目管理专家，负责FDE项目的全流程管控。

你的核心职责：
1. 进度跟踪：实时跟踪项目各阶段进度，识别延期风险
2. 风险预警：自动识别技术风险、业务风险、资源风险，提前预警
3. 文档生成：自动生成项目周报、交付文档、复盘报告
4. 资产沉淀：将项目中的通用组件、最佳实践、踩坑经验沉淀到记忆图谱
5. 多项目管理：支持FDE同时管理多个项目，提供资源视图与协调建议

工作原则：
- 数据驱动：所有判断基于项目实际数据，不臆测
- 提前预警：风险在变成问题之前识别出来
- 自动沉淀：项目经验自动归档，跨项目复用
- 简洁高效：文档直击要点，不写废话

输出格式要求：
- 进度报告：阶段完成度 + 关键里程碑 + 延期风险 + 下一步计划
- 风险清单：风险描述 + 影响等级 + 发生概率 + 应对措施 + 负责人
- 周报：本周完成 + 下周计划 + 风险问题 + 需要支持
- 复盘报告：目标达成情况 + 做得好的 + 需改进的 + 经验教训 + 行动项
"""

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """根据task_type分发"""
        task_type = input_data.get("task_type", "progress_report")
        handlers = {
            "progress_report": self._progress_report,
            "risk_alert": self._risk_alert,
            "weekly_report": self._weekly_report,
            "delivery_doc": self._delivery_doc,
            "retrospective": self._retrospective,
            "asset_sediment": self._asset_sediment,
        }
        handler = handlers.get(task_type, self._progress_report)
        return await handler(input_data)

    async def _progress_report(self, input_data: dict[str, Any]) -> AgentResult:
        """生成进度报告"""
        project_data = input_data.get("project_data", {})
        tasks = input_data.get("tasks", [])

        completed = sum(1 for t in tasks if t.get("status") == "completed")
        total = len(tasks)
        progress = completed / total if total > 0 else 0

        # 识别延期任务
        delayed = [
            t for t in tasks if t.get("status") != "completed" and t.get("due_date", "") < str(datetime.now().date())
        ]

        report = {
            "project_id": self.project_id,
            "project_name": project_data.get("name", ""),
            "current_phase": project_data.get("status", "research"),
            "overall_progress": round(progress, 2),
            "completed_tasks": completed,
            "total_tasks": total,
            "delayed_tasks": [{"id": t.get("id"), "name": t.get("title"), "delay_days": 3} for t in delayed],
            "key_milestones": self._get_milestones(project_data.get("status", "research")),
            "next_steps": self._get_next_steps(project_data.get("status", "research")),
            "health_status": "green" if not delayed and progress >= 0.5 else ("yellow" if not delayed else "red"),
        }

        return AgentResult(
            success=True,
            content=f"项目整体进度{progress * 100:.0f}%，当前阶段[{report['current_phase']}]，健康状态[{report['health_status']}]。",
            structured_output=report,
            metadata={"delayed_count": len(delayed)},
        )

    async def _risk_alert(self, input_data: dict[str, Any]) -> AgentResult:
        """风险预警"""
        project_data = input_data.get("project_data", {})
        recent_events = input_data.get("recent_events", [])

        risks = self._identify_risks(project_data, recent_events)

        return AgentResult(
            success=True,
            content=f"识别出{len(risks)}个风险，其中高风险{sum(1 for r in risks if r['level'] == 'high')}个。",
            structured_output={"risks": risks, "alert_time": datetime.now().isoformat()},
            metadata={"high_risk_count": sum(1 for r in risks if r["level"] == "high")},
        )

    def _identify_risks(self, project_data: dict, events: list) -> list[dict]:
        """识别项目风险"""
        risks = []
        # 基于规则的风险识别（实际用LLM）
        status = project_data.get("status", "research")
        if status == "research":
            risks.append(
                {
                    "id": "R1",
                    "risk": "客户文档不完整，可能影响需求准确性",
                    "level": "medium",
                    "probability": "medium",
                    "impact": "需求基线质量下降",
                    "mitigation": "主动向客户索要补充资料，设置人工审核节点",
                    "owner": "FDE",
                }
            )
        if status == "iteration":
            risks.append(
                {
                    "id": "R2",
                    "risk": "Badcase积累过多，夜间迭代可能无法全部修复",
                    "level": "high",
                    "probability": "high",
                    "impact": "版本质量下降",
                    "mitigation": "限制每轮迭代Badcase数量，优先修复高严重度问题",
                    "owner": "FDE",
                }
            )
        risks.append(
            {
                "id": "R3",
                "risk": "LLM API不稳定，可能影响交付进度",
                "level": "medium",
                "probability": "medium",
                "impact": "任务执行延迟",
                "mitigation": "多模型兜底+重试机制",
                "owner": "技术",
            }
        )
        return risks

    async def _weekly_report(self, input_data: dict[str, Any]) -> AgentResult:
        """生成周报"""
        week_data = input_data.get("week_data", {})
        report = {
            "week": week_data.get("week", f"W{datetime.now().isocalendar()[1]}"),
            "project_name": week_data.get("project_name", ""),
            "completed_this_week": week_data.get("completed", ["调研分析完成", "需求基线确认", "方案设计完成"]),
            "planned_next_week": week_data.get("planned", ["代码开发", "知识库构建", "第一轮迭代"]),
            "risks_and_issues": week_data.get("risks", ["LLM API偶尔不稳定"]),
            "support_needed": week_data.get("support", ["需客户确认业务规则细节"]),
            "metrics": {"tasks_completed": 5, "code_lines_generated": 1200, "benchmark_accuracy": 0.85},
        }
        return AgentResult(success=True, content=f"第{report['week']}周周报已生成。", structured_output=report)

    async def _delivery_doc(self, input_data: dict[str, Any]) -> AgentResult:
        """生成交付文档"""
        doc_type = input_data.get("doc_type", "delivery_summary")
        doc = {
            "doc_type": doc_type,
            "project_id": self.project_id,
            "generated_at": datetime.now().isoformat(),
            "content": {
                "project_overview": "项目背景与目标概述",
                "deliverables": ["需求基线文档", "技术方案文档", "项目代码", "知识库", "评测报告", "用户手册"],
                "acceptance_results": {"functional": "通过", "performance": "通过", "security": "通过"},
                "known_limitations": ["复杂多轮对话场景需人工介入", "极端非标业务规则需定制开发"],
                "handover_notes": "运维交接说明与后续维护建议",
            },
        }
        return AgentResult(success=True, content=f"交付文档[{doc_type}]已生成。", structured_output=doc)

    async def _retrospective(self, input_data: dict[str, Any]) -> AgentResult:
        """生成复盘报告"""
        retro = {
            "project_id": self.project_id,
            "goal_achievement": {"planned": "10天交付MVP", "actual": "12天交付MVP", "achievement_rate": 0.92},
            "what_went_well": ["AI主导调研大幅提升效率", "Benchmark前置有效减少需求扯皮", "夜间迭代机制验证可行"],
            "what_to_improve": [
                "复杂业务规则理解仍需人工辅助",
                "代码生成质量在复杂场景不稳定",
                "记忆跨项目复用效果有待提升",
            ],
            "lessons_learned": [
                "验证前置是AI项目成功的关键",
                "AI主导+人工决策是当前最优模式",
                "记忆沉淀需要持续投入才能形成飞轮",
            ],
            "action_items": [
                {"action": "优化业务规则理解Prompt", "owner": "FDE", "priority": "high"},
                {"action": "增加代码生成后的自动测试覆盖率", "owner": "技术", "priority": "medium"},
            ],
        }
        return AgentResult(success=True, content="项目复盘报告已生成。", structured_output=retro)

    async def _asset_sediment(self, input_data: dict[str, Any]) -> AgentResult:
        """资产沉淀：将项目经验写入记忆图谱"""
        assets = input_data.get("assets", [])
        sediment_count = 0
        for asset in assets:
            await self.memory.remember(
                content=f"[资产沉淀-{asset.get('type', 'general')}] {asset.get('content', '')}",
                metadata={
                    "asset_type": asset.get("type"),
                    "project_id": self.project_id,
                    "reusable": asset.get("reusable", True),
                },
            )
            sediment_count += 1

        return AgentResult(
            success=True,
            content=f"已沉淀{sediment_count}项项目资产到记忆图谱，可跨项目复用。",
            structured_output={
                "sedimented_count": sediment_count,
                "asset_types": list(set(a.get("type", "general") for a in assets)),
            },
        )

    def _get_milestones(self, status: str) -> list[dict]:
        """获取关键里程碑"""
        milestones = {
            "research": [{"name": "需求基线确认", "status": "in_progress", "due": "Day3"}],
            "design": [
                {"name": "需求基线确认", "status": "completed", "due": "Day3"},
                {"name": "方案设计评审", "status": "in_progress", "due": "Day5"},
            ],
            "iteration": [
                {"name": "需求基线确认", "status": "completed"},
                {"name": "方案设计评审", "status": "completed"},
                {"name": "MVP首版交付", "status": "in_progress", "due": "Day10"},
            ],
            "delivered": [{"name": "全部里程碑", "status": "completed"}],
        }
        return milestones.get(status, [])

    def _get_next_steps(self, status: str) -> list[str]:
        """获取下一步计划"""
        steps = {
            "research": ["完成文档解析", "生成需求基线", "组织需求评审"],
            "design": ["生成产品/技术/验证方案", "方案交叉校验", "组织方案评审"],
            "iteration": ["代码开发与知识库构建", "每日版本迭代", "收集用户反馈"],
            "delivered": ["项目复盘", "资产沉淀", "客户培训"],
        }
        return steps.get(status, [])
