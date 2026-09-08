"""
外部生态集成层（v0.3.0 四大卖点编排）

卖点拼图（本项目深做 1+2，生态集成 3+4）：
  1. 本体抽取→业务建模→需求分析     ← 本项目（agents/research）
  2. 自动知识库 + 自动化 Benchmark   ← 本项目（tools/knowledge_base, benchmark）
  3. 大批量自动化 vibe coding       ← night-factory（兄弟项目，工单制夜间无人值守）
  4. 自动化测试/验收执行            ← 外部 RPA 项目（webhook 对接）

关键数据流（验证前置方法论的跨产品贯穿）：
  需求基线.acceptance_criteria  →  night-factory 工单.acceptance[]
  Benchmark 测试集              →  RPA 执行用例
"""

from .night_factory import export_tickets_json, generate_tickets
from .rpa_runner import ExternalRpaRunner, RpaRunner, get_rpa_runner

__all__ = [
    "generate_tickets",
    "export_tickets_json",
    "RpaRunner",
    "ExternalRpaRunner",
    "get_rpa_runner",
]
