"""
交付物导出（v0.1.2 B1）：项目数据 → 可交付文档

导出条目（每个项目最多 6 份交付物）：
  01-项目概览 / 02-需求基线 / 03-方案设计 / 04-Benchmark测试集 / 05-迭代报告 / 06-评审记录

输出格式：
  markdown  : 纯 Python 渲染，零依赖
  docx      : python-docx 渲染（未安装时自动降级 markdown 并提示）
  打包      : zip（format=md|docx → 返回 zip 文件流）
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..storage import get_storage


@dataclass
class Deliverable:
    """一份可交付文档"""

    key: str  # 文件名主干，如 02-需求基线
    title: str
    markdown: str


# ===== 数据组装 =====


def build_deliverables(project_id: str) -> list[Deliverable]:
    """从存储组装项目的全部交付物（缺数据的部分自动跳过）"""
    storage = get_storage()
    project = storage.get_project(project_id)
    if project is None:
        raise ValueError(f"项目不存在: {project_id}")

    deliverables: list[Deliverable] = []

    def add(key: str, title: str, md: Optional[str]):
        if md:
            deliverables.append(Deliverable(key=key, title=title, markdown=md))

    # 01 项目概览
    add("01-项目概览", "项目概览", _render_overview(project, storage))
    # 02 需求基线
    baseline = project.get("requirements_baseline") or {}
    if baseline:
        add("02-需求基线", "需求基线", _render_baseline(project, baseline))
    # 03 方案设计
    solutions = project.get("solutions") or {}
    if solutions:
        add("03-方案设计", "三方案设计", _render_solutions(project, solutions))
    # 04 Benchmark 测试集
    benchmarks = storage.list_benchmarks(project_id)
    if benchmarks:
        add("04-Benchmark测试集", "Benchmark 测试集", _render_benchmarks(project, benchmarks))
    # 05 迭代报告
    add("05-迭代报告", "迭代报告", _render_iterations(project_id, storage))
    # 06 评审记录
    reviews = storage.list_reviews()
    reviews = [r for r in reviews if r.get("project_id") == project_id]
    if reviews:
        add("06-评审记录", "评审记录", _render_reviews(project, reviews))

    # 07 复盘报告（v0.2.0 D1：有执行数据即生成）
    from .retrospective import build_retrospective

    markdown, _stats = build_retrospective(project_id)
    add("07-复盘报告", "项目复盘", markdown)

    return deliverables


# ===== Markdown 渲染 =====


def _ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return "-"


def _render_overview(project: dict, storage) -> str:
    pid = project["id"]
    tasks = storage.list_tasks(pid)
    docs = storage.list_documents(pid)
    completed = sum(1 for t in tasks if t.get("status") == "completed")
    status_map = {"research": "调研分析", "design": "方案设计", "delivery": "开发交付", "iteration": "迭代运营"}
    lines = [
        f"# 项目概览：{project.get('name', '-')}",
        "",
        f"> 客户：{project.get('client_name', '-')} ｜ 行业：{project.get('industry', '-')} ｜ 状态：{status_map.get(project.get('status'), project.get('status', '-'))}",
        "",
        "## 基本信息",
        "",
        f"- 项目ID：`{pid}`",
        f"- 创建时间：{_ts(project.get('created_at'))}",
        f"- 项目描述：{project.get('description') or '-'}",
        "",
        "## 执行统计",
        "",
        f"- 任务总数：{len(tasks)}（已完成 {completed}）",
        f"- 已上传文档：{len(docs)} 份",
    ]
    if docs:
        lines += ["", "## 文档清单", "", "| 文件名 | 解析状态 | 上传时间 |", "| --- | --- | --- |"]
        lines += [
            f"| {doc.get('filename', '-')} | {doc.get('parse_status', '-')} | {_ts(doc.get('uploaded_at', doc.get('created_at')))} |"
            for doc in docs
        ]
    return "\n".join(lines) + "\n"


def _render_baseline(project: dict, b: dict) -> str:
    lines = [f"# 需求基线：{project.get('name', '-')}", ""]
    if b.get("summary"):
        lines += [f"> {b['summary']}", ""]

    # 业务流程
    bp = b.get("business_process") or {}
    if bp:
        lines += ["## 业务流程", ""]
        nodes = bp.get("nodes") or []
        if nodes:
            lines += ["| 节点 | 频率 | 自动化潜力 | ROI |", "| --- | --- | --- | --- |"]
            lines += [
                f"| {n.get('name', n.get('id', '-'))}（{n.get('id', '')}） | {n.get('frequency', '-')} | {n.get('automation_potential', '-')} | {n.get('roi_score', '-')} |"
                for n in nodes
            ]
            lines.append("")
        for flow in bp.get("flows") or []:
            lines.append(f"- 流程：{flow}")
        if bp.get("pain_points"):
            lines += ["", "### 痛点", ""] + [f"- {p}" for p in bp["pain_points"]]
        if bp.get("automation_candidates"):
            lines += ["", "### 自动化候选节点", "", "| 节点 | 原因 | 预估节省 |", "| --- | --- | --- |"]
            lines += [
                f"| {c.get('node_id', '-')} | {c.get('reason', '-')} | {c.get('estimated_saving', '-')} |"
                for c in bp["automation_candidates"]
            ]
        lines.append("")

    # 数据资产
    da = b.get("data_assets") or {}
    if da:
        lines += ["## 数据资产", ""]
        datasets = da.get("datasets") or []
        if datasets:
            lines += ["| 数据集 | 来源 | 格式 | 质量 | 接入成本 | 敏感度 |", "| --- | --- | --- | --- | --- | --- |"]
            lines += [
                f"| {d.get('name', '-')} | {d.get('source', '-')} | {d.get('format', '-')} | {d.get('quality_score', '-')} | {d.get('access_cost', '-')} | {d.get('sensitivity', '-')} |"
                for d in datasets
            ]
            lines.append("")
        if da.get("quality_issues"):
            lines += ["**质量问题**"] + [f"- {q}" for q in da["quality_issues"]] + [""]
        if da.get("access_plan"):
            lines += ["", f"**接入方案**：{da['access_plan']}", ""]

    # 需求规格
    req = b.get("requirements") or {}
    if req:
        lines += ["## 需求规格", "", "### 功能需求", ""]
        func = req.get("functional") or []
        if func:
            lines += ["| ID | 需求 | 描述 | 优先级 | 验收标准 |", "| --- | --- | --- | --- | --- |"]
            lines += [
                f"| {r.get('id', '-')} | {r.get('title', '-')} | {r.get('description', '-')} | {r.get('priority', '-')} | {r.get('acceptance_criteria', '-')} |"
                for r in func
            ]
        else:
            lines.append("（无）")
        nf = req.get("non_functional") or []
        if nf:
            lines += ["", "### 非功能需求", "", "| 类别 | 描述 | 指标 |", "| --- | --- | --- |"]
            lines += [
                f"| {n.get('category', '-')} | {n.get('description', '-')} | {n.get('target', '-')} |" for n in nf
            ]
        if req.get("mvp_scope"):
            lines += ["", f"**MVP 范围**：{'、'.join(req['mvp_scope'])}"]
        risks = req.get("risks") or []
        if risks:
            lines += ["", "### 风险", "", "| 风险 | 影响 | 应对 |", "| --- | --- | --- |"]
            lines += [f"| {r.get('risk', '-')} | {r.get('impact', '-')} | {r.get('mitigation', '-')} |" for r in risks]
        lines.append("")

    # Benchmark 验收标准（详细用例在 04）
    bench = b.get("benchmark") or {}
    ac = bench.get("acceptance_criteria") or {}
    if ac:
        lines += ["## 验收标准（Benchmark 先行）", ""]
        lines += [f"- {k}：{v}" for k, v in ac.items()]
        hb = bench.get("human_baseline") or {}
        if hb:
            lines += ["", "**人工基线对比**：" + "；".join(f"{k}={v}" for k, v in hb.items())]
        lines.append("")

    return "\n".join(lines)


def _render_solutions(project: dict, s: dict) -> str:
    lines = [f"# 三方案设计：{project.get('name', '-')}", ""]
    if s.get("summary"):
        lines += [f"> {s['summary']}", ""]

    prod = s.get("product_solution") or {}
    if prod:
        lines += ["## 一、产品方案", ""]
        features = prod.get("features") or []
        if features:
            lines += ["| ID | 功能 | 模块 | 优先级 | 描述 |", "| --- | --- | --- | --- | --- |"]
            lines += [
                f"| {f.get('id', '-')} | {f.get('name', '-')} | {f.get('module', '-')} | {f.get('priority', '-')} | {f.get('description', '-')} |"
                for f in features
            ]
            lines.append("")
        for flow in prod.get("interaction_flows") or []:
            lines.append(f"- 交互流程：{flow}")
        if prod.get("architecture_mermaid"):
            lines += ["", "**功能架构（Mermaid）**", "", "```mermaid", prod["architecture_mermaid"].strip(), "```"]
        lines.append("")

    tech = s.get("tech_solution") or {}
    if tech:
        lines += ["## 二、技术方案", ""]
        if tech.get("architecture_mermaid"):
            lines += ["**系统架构（Mermaid）**", "", "```mermaid", tech["architecture_mermaid"].strip(), "```", ""]
        interfaces = tech.get("interfaces") or []
        if interfaces:
            lines += ["**接口清单**", "", "| 接口 | 方法 | 描述 |", "| --- | --- | --- |"]
            lines += [
                f"| {i.get('path', i.get('name', '-'))} | {i.get('method', '-')} | {i.get('description', '-')} |"
                for i in interfaces
            ]
            lines.append("")
        risks = tech.get("risks") or []
        if risks:
            lines += ["**技术风险**", "", "| 风险 | 影响 | 应对 |", "| --- | --- | --- |"]
            lines += [
                f"| {r.get('risk', r.get('description', '-'))} | {r.get('impact', '-')} | {r.get('mitigation', '-')} |"
                for r in risks
            ]
            lines.append("")

    val = s.get("validation_solution") or {}
    if val:
        lines += ["## 三、验证方案", ""]
        tcs = val.get("test_cases") or []
        if tcs:
            lines += ["| 用例 | 类型 | 描述 |", "| --- | --- | --- |"]
            lines += [
                f"| {t.get('id', t.get('name', '-'))} | {t.get('type', '-')} | {t.get('description', t.get('scenario', '-'))} |"
                for t in tcs
            ]
            lines.append("")

    cc = s.get("cross_check") or {}
    if cc:
        lines += ["## 交叉校验", ""]
        consistent = cc.get("consistent", cc.get("all_consistent"))
        if consistent is not None:
            lines += [f"- 方案一致性：{'✅ 一致' if consistent else '⚠️ 存在冲突'}"]
        for conf in cc.get("conflicts", []) or []:
            lines.append(f"- ⚠️ 冲突：{conf}")
        for rec in cc.get("recommendations", []) or []:
            lines.append(f"- 建议：{rec}")

    return "\n".join(lines) + "\n"


def _render_benchmarks(project: dict, benchmarks: list[dict]) -> str:
    lines = [f"# Benchmark 测试集：{project.get('name', '-')}", ""]
    for bm in benchmarks:
        lines += [
            f"## {bm.get('benchmark_id', '-')}",
            "",
            f"> 生成时间：{_ts(bm.get('created_at'))} ｜ 用例数：{bm.get('case_count', '-')}",
            "",
        ]
        tcs = bm.get("test_cases") or []
        if tcs:
            lines += ["| ID | 输入 | 预期输出 | 类别 | 难度 |", "| --- | --- | --- | --- | --- |"]
            lines += [
                f"| {t.get('id', '-')} | {str(t.get('input', '-'))[:80]} | {str(t.get('expected_output', '-'))[:80]} | {t.get('category', '-')} | {t.get('difficulty', '-')} |"
                for t in tcs
            ]
        lines.append("")
    return "\n".join(lines)


def _render_iterations(project_id: str, storage) -> Optional[str]:
    tasks = [
        t
        for t in storage.list_tasks(project_id)
        if t.get("type") == "nightly_iteration" and t.get("status") == "completed"
    ]
    if not tasks:
        return None
    lines = ["# 夜间迭代报告", ""]
    for i, t in enumerate(tasks, 1):
        r = t.get("result") or {}
        gate = "✅ 通过" if r.get("gate_passed") else "❌ 拦截"
        dep = "已部署" if r.get("deployed") else ("已回滚" if r.get("rolled_back") else "未部署")
        lines += [
            f"## 迭代 {i}（{r.get('version', '-')}）",
            "",
            f"- 时间：{_ts(t.get('created_at'))}",
            f"- 自动修复：{r.get('auto_fixed', 0)} ｜ 待人工：{r.get('need_human', 0)}",
            f"- 回归准确率：{r.get('regression_accuracy', 0):.2%}",
            f"- 质量门禁：{gate} ｜ 状态：{dep}",
            "",
        ]
        report = r.get("report")
        if isinstance(report, str) and report.strip():
            lines += ["### 详细报告", "", "```", report.strip()[:3000], "```", ""]
    return "\n".join(lines)


def _render_reviews(project: dict, reviews: list[dict]) -> str:
    status_map = {"pending": "⏳ 待审", "approved": "✅ 通过", "rejected": "❌ 驳回", "auto_approved": "☑️ 自动通过"}
    lines = [
        f"# 评审记录：{project.get('name', '-')}",
        "",
        "| 评审ID | 类型 | 状态 | 评审人 | 时间 | 备注 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {r.get('review_id', '-')} | {r.get('type', '-')} | {status_map.get(r.get('status'), r.get('status', '-'))} | {r.get('reviewer', '-')} | {_ts(r.get('created_at'))} | {r.get('comment', '') or ''} |"
        for r in reviews
    ]
    return "\n".join(lines) + "\n"


# ===== 打包 =====


def export_zip(project_id: str, fmt: str = "md") -> tuple[str, bytes]:
    """
    导出全部交付物为 zip。
    fmt: md（markdown 文件）/ docx（Word 文件，python-docx 未安装时降级 md）
    返回 (filename, zip_bytes)
    """
    storage = get_storage()
    project = storage.get_project(project_id)
    if project is None:
        raise ValueError(f"项目不存在: {project_id}")

    deliverables = build_deliverables(project_id)
    # HTTP 头安全文件名：仅 ASCII（zip 内部条目名保留中文）
    ext = "docx" if fmt == "docx" else "md"
    pid8 = project_id.replace("-", "")[:8]
    filename = f"aifde-{pid8}-deliverables-{datetime.now().strftime('%Y%m%d')}.{ext}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        readme = [
            f"# {project.get('name', '')} 交付物包",
            "",
            f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 格式：{ext}",
            "",
            "## 包含文件",
            "",
        ]
        for d in deliverables:
            if fmt == "docx":
                content = _docx_bytes(d)
                if content is None:  # python-docx 未装 → 降级 md
                    zf.writestr(f"{d.key}.md", d.markdown)
                    readme.append(f"- {d.key}.md（docx 不可用，已降级 markdown）")
                    continue
                zf.writestr(f"{d.key}.docx", content)
                readme.append(f"- {d.key}.docx")
            else:
                zf.writestr(f"{d.key}.md", d.markdown)
                readme.append(f"- {d.key}.md")
        zf.writestr("README.md", "\n".join(readme) + "\n")
    return filename, buf.getvalue()


def _docx_bytes(d: Deliverable) -> Optional[bytes]:
    """python-docx 渲染（轻量 Markdown → DOCX）；未安装返回 None"""
    try:
        from .docx_renderer import markdown_to_docx
    except ImportError:
        return None
    return markdown_to_docx(d.title, d.markdown)
