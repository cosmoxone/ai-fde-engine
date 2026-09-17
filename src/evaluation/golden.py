"""
需求基线黄金集（v0.1.2 B3）

用途：真实 LLM 环境下的调研输出质量回归基线（人工标注要点命中评估）。
- 20 条样本：制造业 8 / 金融 6 / 政务 6
- 每条 = 文档片段 + 客户诉求 + 期望要点（关键词级，人工评审提炼）
- 评估：ResearchAgent 生成需求基线后，统计要点命中率（目标 ≥80%，商业计划 §4）

运行：python -m src.evaluation.golden（需配置真实 LLM Key；mock 模式跳过并提示）
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GoldenSample:
    sample_id: str
    industry: str
    doc_snippet: str  # 客户文档片段
    client_ask: str  # 客户原始诉求
    expected_points: list[str] = field(default_factory=list)  # 需求基线应覆盖的要点关键词


GOLDEN_SAMPLES: list[GoldenSample] = [
    # ===== 制造业 8 条 =====
    GoldenSample(
        "M1",
        "制造业",
        "质检员根据SIP文件执行IQC，A类物料按GB/T 2828.1抽样，AQL=0.65。来料异常需8小时内出具处置意见。物料标准分散在300多份PDF中。",
        "让质检员快速查到检验标准",
        ["IQC", "抽样", "标准"],
    ),
    GoldenSample(
        "M2",
        "制造业",
        "产线IPQC记录写入MES，过程巡检每2小时一次。CPK低于1.33需停线分析。异常处理依赖班组长经验判断。",
        "过程质量异常自动预警",
        ["IPQC", "CPK", "预警", "异常"],
    ),
    GoldenSample(
        "M3",
        "制造业",
        "不合格品由MRB评审处置：返工/让步/报废三类。让步放行必须取得客户书面特采许可并记录追溯。",
        "不合格品处置流程数字化",
        ["MRB", "让步", "追溯"],
    ),
    GoldenSample(
        "M4",
        "制造业",
        "客诉从收到回复需24小时内。客诉分析报告需引用历史相似案例，目前靠质量工程师翻Excel案例库。",
        "客诉根因分析提效",
        ["客诉", "案例", "根因"],
    ),
    GoldenSample(
        "M5",
        "制造业",
        "供应商来料批次合格率月度汇总，评价分低于80分启动辅导。数据从ERP采购模块与QMS质检模块手工汇总。",
        "供应商质量看板自动化",
        ["供应商", "合格率", "看板", "汇总"],
    ),
    GoldenSample(
        "M6",
        "制造业",
        "新品试产阶段SIP文件频繁变更，版本混乱导致检验员用旧版本。SIP变更需质量部审批发布。",
        "检验规范版本管理",
        ["SIP", "版本", "变更", "审批"],
    ),
    GoldenSample(
        "M7",
        "制造业",
        "计量器具按周期送检，超期器具不得使用。目前在Excel台账管理，经常漏检。",
        "计量器具到期提醒",
        ["计量", "周期", "提醒", "台账"],
    ),
    GoldenSample(
        "M8",
        "制造业",
        "8D报告编写耗时：D2问题描述与D4根因分析最耗时，需聚合多系统数据。客户要求重大质量事件5个工作日出8D。",
        "8D报告自动生成初稿",
        ["8D", "根因", "生成"],
    ),
    # ===== 金融 6 条 =====
    GoldenSample(
        "F1",
        "金融业",
        "理财产品条款库含200+产品。客服答复必须引用条款原文，禁止口头承诺收益。保本类话术违规将追责。",
        "客服答复合规提速",
        ["条款", "引用", "合规"],
    ),
    GoldenSample(
        "F2",
        "金融业",
        "投诉工单要求2小时首响。历史投诉案例未结构化，新人处理耗时是老人的3倍。",
        "投诉处理辅助",
        ["投诉", "案例", "首响"],
    ),
    GoldenSample(
        "F3",
        "金融业",
        "销售适当性：客户风险测评等级与产品风险等级必须匹配，超风险销售禁止。销售过程需双录。",
        "适当性核查自动化",
        ["适当性", "风险", "匹配", "双录"],
    ),
    GoldenSample(
        "F4",
        "金融业",
        "保险条款术语晦涩，客户常问等待期/免赔额/现金价值。客服培训周期6周。",
        "保险条款智能问答",
        ["等待期", "免赔", "培训", "问答"],
    ),
    GoldenSample(
        "F5",
        "金融业",
        "反洗钱可疑交易识别后需上报，报告要素多且格式严格。每月约50笔可疑交易需人工撰写报告。",
        "可疑交易报告辅助生成",
        ["反洗钱", "可疑", "报告"],
    ),
    GoldenSample(
        "F6",
        "金融业",
        "监管新规下发后，全部对外话术需在3个工作日内完成合规更新。目前人工逐条排查更新。",
        "话术合规批量更新",
        ["话术", "更新", "合规", "排查"],
    ),
    # ===== 政务 6 条 =====
    GoldenSample(
        "G1",
        "政务",
        "政务服务事项指南3000余项，高频事项约200项。市民口语化提问与事项名称差异大。",
        "办事指南精准问答",
        ["事项", "指南", "问答", "高频"],
    ),
    GoldenSample(
        "G2",
        "政务",
        "12345热线高峰接通率不足60%。咨询类诉求占比70%，多数可知识库直接答复。",
        "热线智能分流",
        ["接通", "分流", "知识库"],
    ),
    GoldenSample(
        "G3",
        "政务",
        "申请材料预审靠窗口人工，材料退件率25%，市民平均跑2.4次才办成。",
        "材料预审减少跑动",
        ["材料", "预审", "退件"],
    ),
    GoldenSample(
        "G4",
        "政务",
        "举报、信访类诉求必须转人工处理并依法保密，不可由智能客服直接答复。",
        "敏感诉求识别转人工",
        ["举报", "信访", "人工", "保密"],
    ),
    GoldenSample(
        "G5",
        "政务",
        "政策文件跨部门口径不一致，市民反映两个部门答复矛盾。需建立统一政策知识库标注生效时间。",
        "政策口径统一",
        ["政策", "口径", "统一", "生效"],
    ),
    GoldenSample(
        "G6",
        "政务",
        "好差评系统显示：答复包含办理时限和材料的评价高4.2分，泛泛答复仅3.1分。",
        "提升答复质量",
        ["好差评", "时限", "质量", "评价"],
    ),
]


async def run_golden_eval(provider_filter: str | None = None, rag_mode: str | None = None) -> dict:
    """
    黄金集评估：真实 LLM 下调研输出 vs 人工要点。

    rag_mode: None=按当前配置（默认 hybrid）；"full"/"hybrid"/"rag" 显式指定——
    v0.4 两栏对比用（18 号 ADR 终验：RAG 模式命中率不得低于 full）。
    返回:
        {status: skipped|done, total, hit_rate, by_industry: {...}, misses: [...],
         input_stats: {avg_prompt_chars, avg_full_chars, avg_reduction}}（done 时）
    """
    from ..config import get_settings

    settings = get_settings()
    if not (settings.deepseek_api_key or settings.qwen_api_key):
        return {
            "status": "skipped",
            "reason": "未配置 LLM API Key（黄金集评估需真实模型输出）",
            "total": len(GOLDEN_SAMPLES),
        }

    from ..agents.research import ResearchAgent
    from ..templates import match_template

    samples = [s for s in GOLDEN_SAMPLES if not provider_filter or s.industry == provider_filter]
    hit_total, point_total = 0, 0
    by_industry: dict[str, list[float]] = {}
    misses: list[dict] = []
    stats_list: list[dict] = []

    for s in samples:
        agent = ResearchAgent(f"golden-{s.sample_id}")
        if rag_mode:
            agent.settings.research_rag_mode = rag_mode  # 评估进程内显式指定（两栏对比）
        pack = match_template(s.industry)
        from ..templates import build_research_context

        if rag_mode and rag_mode != "full":
            # 两栏对比前提：样本文档先入 KB（每样本独立项目，Embedded 同步索引即写即检）
            # ——否则 hybrid 检索空命中自动回退 full，两栏失真（对比无意义）
            from ..knowledge import DocSpec, get_knowledge_gateway

            get_knowledge_gateway().ingest_documents(
                f"golden-{s.sample_id}",
                [
                    DocSpec(
                        title=f"{s.sample_id}.md",
                        content=s.doc_snippet,
                        metadata={"doc_id": s.sample_id, "origin": "golden-eval"},
                    )
                ],
            )

        result = await agent.execute(
            {
                "documents": [{"filename": f"{s.sample_id}.md", "content": s.doc_snippet}],
                "client_requirements": s.client_ask,
                "industry_context": build_research_context(pack) if pack else "",
            }
        )
        baseline = result.structured_output or {}
        text = json_dump_for_match(baseline)
        if isinstance(result.metadata.get("input_stats"), dict):
            stats_list.append(result.metadata["input_stats"])

        sample_hits = 0
        for point in s.expected_points:
            point_total += 1
            if point.lower() in text.lower():
                sample_hits += 1
                hit_total += 1
            else:
                misses.append({"sample": s.sample_id, "industry": s.industry, "point": point})
        by_industry.setdefault(s.industry, []).append(sample_hits / len(s.expected_points))

    industry_rates = {k: sum(v) / len(v) for k, v in by_industry.items()}
    avg = lambda key: (sum(s.get(key, 0) for s in stats_list) / len(stats_list)) if stats_list else 0  # noqa: E731
    return {
        "status": "done",
        "total": len(samples),
        "hit_rate": round(hit_total / point_total, 4) if point_total else 0.0,
        "by_industry": {k: round(v, 4) for k, v in industry_rates.items()},
        "misses": misses,
        "input_stats": {
            "avg_prompt_chars": round(avg("prompt_chars")),
            "avg_full_chars": round(avg("full_chars")),
            "avg_reduction": round(avg("reduction"), 3),
        },
        "note": "目标：命中率≥80%（docs/10-商业计划 §4 价值层①验收）",
    }


async def run_golden_rag_compare() -> dict:
    """v0.4 两栏对比（18 号 ADR 终验协议）：full × hybrid(/rag) 同集双跑。

    判据：rag 栏 hit_rate ≥ full 栏（≥100% 不倒退）方可确认 RAG 化默认模式；
    倒退则按 18 号 §6 预案回退（research_rag_mode 默认改 full）。
    无 Key 时返回 skipped（与 run_golden_eval 同语义）。
    """
    modes = ("full", "hybrid")
    columns = {}
    for mode in modes:
        res = await run_golden_eval(rag_mode=mode)
        if res.get("status") != "done":
            return {"status": "skipped", "reason": res.get("reason", "未配置 Key"), "mode": mode}
        columns[mode] = res
    verdict = "pass" if columns["hybrid"]["hit_rate"] >= columns["full"]["hit_rate"] else "regress"
    return {
        "status": "done",
        "verdict": verdict,
        "columns": columns,
        "note": "pass=RAG 化维持；regress=按 18 号预案回退 full 默认",
    }


def json_dump_for_match(data: dict) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, default=str)


def main() -> None:
    """CLI 入口：python -m src.evaluation.golden"""
    import asyncio

    result = asyncio.run(run_golden_eval())
    if result["status"] == "skipped":
        print(f"⏭️ 跳过：{result['reason']}")
        print("   配置方式：Dashboard 设置页填入 DeepSeek/Qwen Key，或 export DEEPSEEK_API_KEY=...")
        return
    print(f"黄金集评估：{result['total']} 条样本")
    print(f"要点命中率：{result['hit_rate']:.1%}（目标 ≥80%）")
    for industry, rate in result["by_industry"].items():
        print(f"  {industry}: {rate:.1%}")
    if result["misses"]:
        print("\n未命中要点：")
        for m in result["misses"]:
            print(f"  [{m['sample']}/{m['industry']}] {m['point']}")


if __name__ == "__main__":
    main()
