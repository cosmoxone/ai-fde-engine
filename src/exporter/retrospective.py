"""
项目复盘报告生成（v0.2.0 D1）

聚合项目全生命周期数据，生成结构化复盘 markdown：
执行概况 / 需求与范围 / 质量与badcase处理 / 评审与人机协同 / 经验沉淀清单
—— FDE 项目结束后 10 分钟产出复盘，经验入库跨项目复用。
"""

from __future__ import annotations

from datetime import datetime

from ..storage import get_storage


def _ts(ts) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "-"


def build_retrospective(project_id: str) -> tuple[str, dict]:
    """返回 (markdown, stats)"""
    storage = get_storage()
    project = storage.get_project(project_id)
    if project is None:
        raise ValueError(f"项目不存在: {project_id}")

    tasks = storage.list_tasks(project_id)
    docs = storage.list_documents(project_id)
    benchmarks = storage.list_benchmarks(project_id)
    badcases = storage.list_badcases(project_id)
    reviews = [r for r in storage.list_reviews() if r.get("project_id") == project_id]

    completed = [t for t in tasks if t.get("status") == "completed"]
    failed = [t for t in tasks if t.get("status") == "failed"]
    iterations = [t for t in tasks if t.get("type") == "nightly_iteration" and t.get("status") == "completed"]
    open_badcases = [b for b in badcases if b.get("status") == "open"]
    approved = [r for r in reviews if r.get("status") == "approved"]

    baseline = project.get("requirements_baseline") or {}
    requirements = (baseline.get("requirements") or {}).get("functional") or []
    mvp_scope = (baseline.get("requirements") or {}).get("mvp_scope") or []
    risks = (baseline.get("requirements") or {}).get("risks") or []

    # 迭代质量汇总
    regression_accs = []
    auto_fixed_total = need_human_total = 0
    fix_suggestions_total = 0
    for t in iterations:
        r = t.get("result") or {}
        if r.get("regression_accuracy"):
            regression_accs.append(r["regression_accuracy"])
        auto_fixed_total += r.get("auto_fixed", 0)
        need_human_total += r.get("need_human", 0)
        fix_suggestions_total += len(r.get("fix_suggestions") or [])
    avg_regression = sum(regression_accs) / len(regression_accs) if regression_accs else None

    stats = {
        "project_id": project_id,
        "task_total": len(tasks),
        "task_completed": len(completed),
        "task_failed": len(failed),
        "iterations": len(iterations),
        "documents": len(docs),
        "benchmarks": len(benchmarks),
        "badcase_total": len(badcases),
        "badcase_open": len(open_badcases),
        "auto_fixed": auto_fixed_total,
        "need_human": need_human_total,
        "review_total": len(reviews),
        "review_approved": len(approved),
        "avg_regression_accuracy": avg_regression,
    }

    lines: list[str] = []
    lines.append(f"# 项目复盘：{project.get('name', project_id)}")
    lines.append("")
    lines.append(
        f"> 客户：{project.get('client_name', '-')} ｜ 行业：{project.get('industry', '-')} ｜ 复盘生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    lines.append("")

    # 1 执行概况
    lines.append("## 1. 执行概况")
    lines.append("")
    lines.append("| 维度 | 数据 |")
    lines.append("| --- | --- |")
    lines.append(f"| 任务 | 总 {len(tasks)}（完成 {len(completed)} / 失败 {len(failed)}） |")
    lines.append(f"| 业务文档 | {len(docs)} 份 |")
    lines.append(f"| Benchmark | {len(benchmarks)} 套 |")
    lines.append(f"| 夜间迭代 | {len(iterations)} 次 |")
    lines.append(
        f"| Badcase | 总 {len(badcases)}（自动修复 {auto_fixed_total} / 待人工 {need_human_total} / 未处理 {len(open_badcases)}） |"
    )
    lines.append(f"| 人工评审 | {len(reviews)} 项（通过 {len(approved)}） |")
    if avg_regression is not None:
        lines.append(f"| 平均回归准确率 | {avg_regression:.1%} |")
    lines.append("")

    # 2 需求与范围
    lines.append("## 2. 需求与范围")
    lines.append("")
    if requirements:
        lines.append(
            f"- 功能需求：{len(requirements)} 条（MVP 范围：{len(mvp_scope)} 条：{'、'.join(mvp_scope) if mvp_scope else '-'}）"
        )
        p0 = sum(1 for r in requirements if r.get("priority") == "P0")
        lines.append(f"- P0 核心需求：{p0} 条")
    else:
        lines.append("- 未生成需求基线")
    if risks:
        lines.append(f"- 已识别风险：{len(risks)} 项")
    lines.append("")

    # 3 质量与badcase处理
    lines.append("## 3. 质量与 Badcase 处理")
    lines.append("")
    if badcases:
        by_type: dict[str, int] = {}
        for b in badcases:
            by_type[b.get("error_type", "unknown")] = by_type.get(b.get("error_type", "unknown"), 0) + 1
        lines.append("| 错误类型 | 数量 |")
        lines.append("| --- | --- |")
        for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
            lines.append(f"| {k} | {v} |")
        lines.append("")
        lines.append(
            f"- 自动修复率：{auto_fixed_total / len(badcases):.0%}（{auto_fixed_total}/{len(badcases)}）"
            if auto_fixed_total
            else "- 自动修复率：0%"
        )
        lines.append(f"- 修复建议产出：{fix_suggestions_total} 条（供人工采纳）" if fix_suggestions_total else "")
    else:
        lines.append("- 无 Badcase 记录（或未进入迭代阶段）")
    lines.append("")

    # 4 评审与人机协同
    lines.append("## 4. 评审与人机协同")
    lines.append("")
    if reviews:
        lines.append("| 评审ID | 类型 | 结果 | 评审人 | 时间 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in reviews[:20]:
            lines.append(
                f"| {r.get('review_id', '-')} | {r.get('type', '-')} | {r.get('status', '-')} | {r.get('reviewer', '-') or '-'} | {_ts(r.get('created_at'))} |"
            )
        lines.append("")
    else:
        lines.append("- 无评审记录")
        lines.append("")

    # 5 经验沉淀清单（下次项目直接复用）
    lines.append("## 5. 经验沉淀清单（跨项目复用）")
    lines.append("")
    lines.append("以下经验已存入本地经验库（跨项目检索可命中）：")
    lines.append("")
    lines.append(f"1. **验收标准模板**：本项目 {len(requirements)} 条量化验收标准可作同类项目起点")
    if benchmarks:
        lines.append(
            f"2. **Benchmark 种子**：{len(benchmarks)} 套测试集（{sum(b.get('case_count', 0) for b in benchmarks)} 条用例）可复用于回归基线"
        )
    if iterations:
        lines.append(
            f"3. **迭代经验**：{len(iterations)} 轮夜间迭代，自动修复 {auto_fixed_total} 例——badcase 归因分布见上表"
        )
    lines.append(
        "4. **行业模板**：若本项目使用了行业模板（" + str(project.get("industry", "-")) + "），本复盘数据可用于模板迭代"
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*由 AI-FDE Engine 生成 · 项目ID `{project_id}`*")

    return "\n".join(lines), stats
