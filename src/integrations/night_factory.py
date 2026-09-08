"""
night-factory 集成（卖点 3：大批量自动化 vibe coding）

将本项目需求基线转换为 night-factory 工单：
- 需求 functional 项 → 工单（objective=需求描述+方案上下文）
- **acceptance_criteria（量化验收标准）→ acceptance[]**：验证前置跨产品贯穿
  ——需求阶段定的验收标准，成为夜间无人值守编码的机械化验收依据
- priority → complexity/budget 映射（P0=high/预算加高）

工单 schema 与 night-factory tasks/*.json 完全兼容（可直接放入其 tasks/ 目录）。
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

# priority → night-factory complexity/budget 映射
_PRIORITY_MAP = {
    "P0": {"complexity": "high", "turns": 30, "tokens": 60000, "wall_time_hours": 2.5},
    "P1": {"complexity": "low", "turns": 16, "tokens": 32000, "wall_time_hours": 1.0},
    "P2": {"complexity": "low", "turns": 10, "tokens": 20000, "wall_time_hours": 0.6},
}


def _split_acceptance(criteria: str) -> list[str]:
    """把验收标准文本拆为机械化可判定的条目列表"""
    if not criteria:
        return ["功能实现并通过既有测试"]
    # 按分号/句号/顿号分隔；保留含量化词的完整子句
    parts = [p.strip() for p in criteria.replace("；", "；").replace(";", "；").split("；") if p.strip()]
    return parts if parts else [criteria]


def generate_tickets(project: dict, repo_path: Optional[str] = None) -> list[dict]:
    """
    需求基线 → night-factory 工单列表。

    project: 项目 dict（含 requirements_baseline）
    repo_path: 目标仓库路径（默认取环境变量 NIGHT_FACTORY_TARGET_REPO）
    """
    baseline = (project or {}).get("requirements_baseline") or {}
    requirements = (baseline.get("requirements") or {}).get("functional") or []
    solutions = (project or {}).get("solutions") or {}
    tech = solutions.get("tech_solution") or {}

    repo = repo_path or os.environ.get("NIGHT_FACTORY_TARGET_REPO", "/path/to/target-repo")
    tickets: list[dict] = []

    for req in requirements:
        priority = req.get("priority", "P1")
        meta = _PRIORITY_MAP.get(priority, _PRIORITY_MAP["P1"])
        rid = req.get("id", f"R{len(tickets) + 1}")

        # objective：需求描述 + 模块归属（来自产品方案）+ 实现边界提示
        objective_parts = [
            f"[FDE/{rid}] {req.get('title', '')}：{req.get('description', '')}",
        ]
        module = _find_module(solutions, rid)
        if module:
            objective_parts.append(f"（归属模块：{module}）")
        if tech.get("tech_stack"):
            stack_names = "、".join(str(s.get("choice", "")) for s in tech["tech_stack"][:3])
            if stack_names:
                objective_parts.append(f"技术栈遵循：{stack_names}")
        objective_parts.append("仅新增实现，不修改既有无关行为。")

        tickets.append(
            {
                "id": f"FDE-{rid}",
                "objective": " ".join(objective_parts),
                "repo_path": repo,
                "complexity": meta["complexity"],
                "budget": {
                    "turns": meta["turns"],
                    "tokens": meta["tokens"],
                    "wall_time_hours": meta["wall_time_hours"],
                },
                "acceptance": _split_acceptance(req.get("acceptance_criteria", "")),
                "source": "ai-fde-engine",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        )
    return tickets


def _find_module(solutions: dict, req_id: str) -> Optional[str]:
    """从产品方案中找需求归属模块（按功能项或模块名提示）"""
    features = (solutions.get("product_solution") or {}).get("features") or []
    for f in features:
        if f.get("id") == req_id or f.get("name") in req_id:
            return f.get("module")
    return None


def export_tickets_json(tickets: list[dict]) -> str:
    """工单列表 → night-factory tasks/*.json 兼容文本"""
    return json.dumps(tickets, ensure_ascii=False, indent=2)
