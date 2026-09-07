"""
行业模板库（v0.1.2 B2）

内置 3 个行业包：制造业质检 / 金融客服 / 政务问答。
每个包包含：调研行业上下文（注入 ResearchAgent）/ 需求模板条目 /
Benchmark 种子用例 / 方案骨架。

扩展点：TemplateSource 抽象（TE 订阅源可替换内置包，见 docs/09 §5.2）。
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

_PACKS_DIR = os.path.join(os.path.dirname(__file__), "packs")


@dataclass
class TemplatePack:
    """行业模板包"""

    key: str  # manufacturing
    industry: str  # 制造业
    name: str  # 智能质检知识库模板
    description: str = ""
    aliases: list[str] = field(default_factory=list)  # 行业别名匹配
    research_hints: dict = field(default_factory=dict)  # 业务节点/痛点/数据资产/合规
    requirement_template: list[dict] = field(default_factory=list)  # 功能需求示例条目
    benchmark_seed: list[dict] = field(default_factory=list)  # 种子测试用例
    solution_skeleton: dict = field(default_factory=dict)  # 常见模块/选型建议


class TemplateSource(ABC):
    """模板源扩展点：CE=内置 JSON；TE=订阅源（远端更新）"""

    @abstractmethod
    def list_packs(self) -> list[TemplatePack]: ...

    @abstractmethod
    def get_pack(self, key: str) -> Optional[TemplatePack]: ...


class BuiltinTemplateSource(TemplateSource):
    """内置 JSON 行业包"""

    def __init__(self) -> None:
        self._packs: dict[str, TemplatePack] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.isdir(_PACKS_DIR):
            return
        for fname in sorted(os.listdir(_PACKS_DIR)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(_PACKS_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
            pack = TemplatePack(
                key=data["key"],
                industry=data["industry"],
                name=data["name"],
                description=data.get("description", ""),
                aliases=data.get("aliases", []),
                research_hints=data.get("research_hints", {}),
                requirement_template=data.get("requirement_template", []),
                benchmark_seed=data.get("benchmark_seed", []),
                solution_skeleton=data.get("solution_skeleton", {}),
            )
            self._packs[pack.key] = pack

    def list_packs(self) -> list[TemplatePack]:
        return list(self._packs.values())

    def get_pack(self, key: str) -> Optional[TemplatePack]:
        return self._packs.get(key)


_source: Optional[TemplateSource] = None


def get_template_source() -> TemplateSource:
    """获取模板源（扩展点：TE 可注册订阅源替换）"""
    global _source
    if _source is None:
        _source = BuiltinTemplateSource()
        from ..extensions import get_registry

        for plugin in get_registry().list_plugins():
            source = plugin.hooks.get("template_source")
            if isinstance(source, TemplateSource):
                _source = source
                break
    return _source


def reset_template_source() -> None:
    global _source
    _source = None


def list_templates() -> list[dict]:
    """行业模板清单（API 用）"""
    return [
        {
            "key": p.key,
            "industry": p.industry,
            "name": p.name,
            "description": p.description,
            "requirement_count": len(p.requirement_template),
            "benchmark_seed_count": len(p.benchmark_seed),
        }
        for p in get_template_source().list_packs()
    ]


def match_template(industry: str) -> Optional[TemplatePack]:
    """按行业名模糊匹配模板包（支持中英文别名）"""
    if not industry:
        return None
    source = get_template_source()
    target = industry.strip().lower()
    for pack in source.list_packs():
        candidates = [pack.key, pack.industry, *pack.aliases]
        for c in candidates:
            c_low = c.lower()
            if c_low == target or (len(target) >= 2 and c_low in target) or (len(c_low) >= 2 and c_low in target):
                return pack
    return None


def build_research_context(pack: TemplatePack) -> str:
    """行业包 → 调研 Agent 的上下文注入文本"""
    h = pack.research_hints
    parts = [f"=== 行业模板上下文：{pack.industry}（{pack.name}） ==="]
    if h.get("business_nodes"):
        parts.append("常见业务节点：" + "、".join(h["business_nodes"]))
    if h.get("pain_points"):
        parts.append("行业典型痛点：" + "；".join(h["pain_points"]))
    if h.get("data_assets"):
        parts.append("常见数据资产：" + "、".join(h["data_assets"]))
    if h.get("compliance"):
        parts.append("合规要求：" + "；".join(h["compliance"]))
    if h.get("terminology"):
        parts.append("行业术语表：" + json.dumps(h["terminology"], ensure_ascii=False))
    return "\n".join(parts)
