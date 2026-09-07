"""
公开评测基准报告（v0.2.0 D3）

可复现的质量基准：内置 Benchmark 种子 × 评测器 → 指标报告。
mock 模式输出基线指标（可复现）；真实 LLM 模式输出黄金集要点命中率对比。

用法：
    python -m src.evaluation.benchmark_report            # 控制台+写 docs/benchmarks/
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from ..config import get_settings
from ..templates import get_template_source
from .evaluator import Evaluator
from .golden import GOLDEN_SAMPLES


async def run_benchmark_report() -> dict:
    """生成公开基准报告数据"""
    settings = get_settings()
    source = get_template_source()
    evaluator = Evaluator("benchmark-report")

    by_industry: dict[str, dict] = {}
    for pack in source.list_packs():
        cases = pack.benchmark_seed
        result = await evaluator.run_benchmark(cases)
        gate_passed, _ = evaluator.check_quality_gate(result)
        by_industry[pack.key] = {
            "industry": pack.industry,
            "cases": len(cases),
            "accuracy": result.accuracy,
            "hallucination_rate": result.hallucination_rate,
            "recall_rate": result.recall_rate,
            "format_compliance": result.format_compliance,
            "gate_passed": gate_passed,
        }

    real_mode = bool(settings.deepseek_api_key or settings.qwen_api_key)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": "real-llm" if real_mode else "mock-baseline",
        "by_industry": by_industry,
        "golden_set": {
            "total": len(GOLDEN_SAMPLES),
            "industries": {
                k: sum(1 for s in GOLDEN_SAMPLES if s.industry == k) for k in {s.industry for s in GOLDEN_SAMPLES}
            },
        },
        "note": (
            "mock-baseline：评测器在种子集上的可复现基线（无LLM依赖）"
            if not real_mode
            else "real-llm：黄金集命中率另见 python -m src.evaluation.golden"
        ),
    }


def render_report(data: dict) -> str:
    lines = [
        "# AI-FDE Engine 公开评测基准",
        "",
        f"> 生成：{data['generated_at']} ｜ 模式：`{data['mode']}`",
        "",
        "## 1. 内置行业种子集 × 评测器基线",
        "",
        "| 行业 | 用例数 | 准确率 | 幻觉率 | 召回率 | 格式合规 | 质量门禁 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, m in data["by_industry"].items():
        lines.append(
            f"| {m['industry']}（{key}） | {m['cases']} | {m['accuracy']:.0%} | "
            f"{m['hallucination_rate']:.1%} | {m['recall_rate']:.0%} | "
            f"{m['format_compliance']:.0%} | {'✅' if m['gate_passed'] else '❌'} |"
        )
    gs = data["golden_set"]
    lines += [
        "",
        "## 2. 需求基线黄金集（人工要点标注）",
        "",
        f"- 样本总数：{gs['total']} 条",
    ]
    lines += [f"  - {k}：{v} 条" for k, v in gs["industries"].items()]
    lines += [
        "",
        "## 3. 复现方式",
        "",
        "```bash",
        "# 本基线（mock，零依赖可复现）",
        "python -m src.evaluation.benchmark_report",
        "",
        "# 真实 LLM 黄金集命中率（配置 DeepSeek/Qwen Key 后）",
        "python -m src.evaluation.golden",
        "```",
        "",
        f"> {data['note']}",
        "",
        "---",
        "",
        "*方法论：验证前置——所有质量结论必须可复现（docs/01 §设计原则）*",
    ]
    return "\n".join(lines)


async def main_async() -> str:
    data = await run_benchmark_report()
    report = render_report(data)
    print(report)
    # 写入 docs/benchmarks/
    import os

    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "docs", "benchmarks"
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "baseline.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n📄 已写入 {out_path}")
    return report


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
