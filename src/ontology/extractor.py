"""本体抽取管线：LLM 结构化抽取 + Mock（行业模板派生）。

设计（13 号 §3.2）：
- 复用已验证的 JSON 能力：chat_json + required_keys 校验重试（v0.1.2 B3 模式）；
- LLM 输出关系以实体名引用，本模块负责 name→id 归一（不匹配的孤儿边丢弃并计数）；
- Mock 模式：制造业行业模板（templates/packs/manufacturing.json research_hints 派生，
  常量内嵌避免文件 IO 脆弱）+ 文档标题派生项目实体——无 Key 也能跑通全流程，
  多文档 merge 后稳定 ≥20 实体 / ≥15 关系（roadmap v0.4-b 验收）。
"""

from __future__ import annotations

import logging

from .types import Entity, Relation, Rule

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM = "你是业务本体抽取引擎。只输出 JSON，不要任何解释文字。"

_EXTRACTION_PROMPT = """从以下业务文档中抽取本体（实体/关系/规则）。输出 JSON，schema：

{{
  "entities": [{{"type": "流程节点|数据资产|系统|角色|物料|合规要求|其他", "name": "实体名(≤20字)", "properties": {{"可选键值": "..."}}, "confidence": 0.9}}],
  "relations": [{{"from": "实体名(必须是 entities 中出现过的)", "to": "实体名(同上)", "relation_type": "属于|触发|产生|依赖|消费|约束|其他"}}],
  "rules": [{{"condition": "条件(业务/合规语句)", "conclusion": "结论", "confidence": 0.9}}]
}}

要求：
1. 实体覆盖业务流程节点、数据资产、系统、角色；关系 15 条起步、实体 20 个起步（信息足够时）；
2. relations 的 from/to 必须引用 entities 中的 name（引用不存在会被丢弃）；
3. 规则含合规红线（如抽检比例、追溯保存年限）；
4. properties 放简短事实（如 {"频率": "每批"}），不放长文本。

文档标题：{title}
文档内容：
{content}
"""

# ---------------------------------------------------------------- Mock 模板（制造业，源自 templates/packs/manufacturing.json research_hints）
_MOCK_NODES = ["来料检验IQC", "过程检验IPQC", "成品检验OQC", "不合格品评审MRB", "质量追溯", "供应商质量管理"]
_MOCK_ASSETS = ["ERP物料主数据", "MES检验记录", "QMS不合格品数据", "检验标准文档库", "客诉记录"]
_MOCK_SYSTEMS = ["ERP系统", "MES系统", "QMS系统", "SRM供应商管理系统"]
_MOCK_ROLES = ["质量工程师", "检验员"]
_MOCK_COMPLIANCE = ["IATF 16949 汽车行业质量体系", "ISO 9001", "产品追溯记录保存要求"]

_MOCK_RULES = [
    ("来料批次到达且供应商为重点级", "执行加严抽检（AQL 0.65）并录入 IQC 记录", 0.9),
    ("检验发现不合格品", "24 小时内提交 MRB 评审并隔离存放", 0.9),
    ("成品出货前", "OQC 全检关键特性并生成出货检验报告", 0.85),
    ("客诉立案", "质量追溯链回溯至来料批次并在 QMS 关联记录", 0.8),
]


def _mock_derive(title: str, content: str) -> tuple[list[Entity], list[Relation], list[Rule]]:
    """行业模板基础本体 + 文档标题派生项目实体（保证多文档 merge 后规模稳定达标）。"""
    entities: list[Entity] = []

    def add(etype: str, name: str, **props) -> Entity:
        ent = Entity(
            id=Entity.make_id(etype, name), type=etype, name=name, properties=props, confidence=0.85, source_docs=[]
        )
        entities.append(ent)
        return ent

    nodes = [add("流程节点", n) for n in _MOCK_NODES]
    assets = [add("数据资产", a) for a in _MOCK_ASSETS]
    systems = [add("系统", s) for s in _MOCK_SYSTEMS]
    add("角色", _MOCK_ROLES[0])
    add("角色", _MOCK_ROLES[1])
    for c in _MOCK_COMPLIANCE:
        add("合规要求", c)

    def rel(a: Entity, b: Entity, rtype: str) -> None:
        relations.append(Relation(a.id, b.id, rtype, []))

    relations: list[Relation] = []
    for i in range(len(nodes) - 1):
        rel(nodes[i], nodes[i + 1], "触发")
    rel(nodes[3], nodes[4], "产生")  # MRB → 质量追溯
    rel(nodes[0], assets[1], "产生")  # IQC → MES检验记录
    rel(nodes[1], assets[1], "产生")  # IPQC → MES检验记录
    rel(nodes[2], assets[2], "产生")  # OQC → QMS不合格品数据
    rel(nodes[3], assets[2], "消费")  # MRB → QMS数据
    rel(nodes[5], assets[3], "消费")  # 供应商质量管理 → 检验标准
    rel(nodes[4], assets[0], "依赖")  # 质量追溯 → ERP物料主数据
    rel(systems[0], assets[0], "属于")  # ERP系统 → ERP主数据
    rel(systems[1], assets[1], "属于")  # MES → MES记录
    rel(systems[2], assets[2], "属于")  # QMS → QMS数据
    rel(systems[2], assets[4], "属于")  # QMS → 客诉记录
    rel(nodes[4], systems[2], "依赖")  # 追溯 → QMS系统
    rel(nodes[5], systems[3], "依赖")  # 供应商管理 → SRM
    rel(systems[3], assets[3], "消费")  # SRM → 检验标准

    rules = [Rule(Rule.make_id(c, k), c, k, conf, []) for c, k, conf in _MOCK_RULES]

    # 文档标题派生：每篇文档一个"项目载体"实体，挂到两个核心节点（多文档增量可累积）
    if title and title.strip():
        proj = add("项目", f"项目:{title.strip()[:24]}", 抽取自="上传文档")
        rel(proj, nodes[0], "依赖")
        rel(proj, systems[2], "依赖")
    return entities, relations, rules


async def extract_ontology(
    title: str,
    content: str,
    llm=None,
    model: str | None = None,
) -> tuple[list[Entity], list[Relation], list[Rule], str]:
    """抽取一篇文档 →（实体, 关系, 规则, 模式）。llm 不可用自动落 Mock。"""
    if llm is None:
        ents, rels, rules = _mock_derive(title, content)
        return ents, rels, rules, "mock"
    try:
        from ..llm.client import LLMMessage

        prompt = _EXTRACTION_PROMPT.format(title=title or "(无题)", content=(content or "")[:20000])
        _, parsed = await llm.chat_json(
            messages=[LLMMessage("system", _EXTRACTION_SYSTEM), LLMMessage("user", prompt)],
            model=model,
            temperature=0.2,
            max_tokens=8000,
        )
        if not parsed or "entities" not in parsed:
            raise ValueError("LLM 输出缺 entities")
        name2id: dict[str, str] = {}
        entities: list[Entity] = []
        for item in parsed.get("entities") or []:
            etype = str(item.get("type") or "").strip()
            name = str(item.get("name") or "").strip()
            if not etype or not name:
                continue
            key = "".join(name.split()).lower()
            eid = Entity.make_id(etype, name)
            name2id.setdefault(key, eid)
            name2id.setdefault(name.lower(), eid)
            entities.append(
                Entity(
                    id=eid,
                    type=etype,
                    name=name,
                    properties=dict(item.get("properties") or {}),
                    confidence=float(item.get("confidence") or 0.8),
                )
            )
        relations: list[Relation] = []
        for item in parsed.get("relations") or []:
            fr = name2id.get("".join(str(item.get("from") or "").split()).lower())
            to = name2id.get("".join(str(item.get("to") or "").split()).lower())
            rt = str(item.get("relation_type") or "").strip()
            if fr and to and rt:
                relations.append(Relation(fr, to, rt))
        rules = [
            Rule(
                Rule.make_id(c := str(i.get("condition") or ""), k := str(i.get("conclusion") or "")),
                c,
                k,
                float(i.get("confidence") or 0.8),
            )
            for i in parsed.get("rules") or []
            if str(i.get("condition") or "").strip() and str(i.get("conclusion") or "").strip()
        ]
        if not entities:
            raise ValueError("LLM 输出无有效实体")
        return entities, relations, rules, "llm"
    except Exception as exc:  # noqa: BLE001 —— LLM 失败降级 Mock（流程可跑通）
        logger.warning("本体 LLM 抽取失败，降级 Mock: %s", exc)
        ents, rels, rules = _mock_derive(title, content)
        return ents, rels, rules, "mock-fallback"
