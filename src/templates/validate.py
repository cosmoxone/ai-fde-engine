"""
行业模板包校验器（v0.2.0 D2）

贡献者本地自检：
    python -m src.templates.validate src/templates/packs/your-pack.json

校验规则（质量红线，社区模板市场的准入门槛）：
  结构：必填字段齐全、类型正确、key 唯一
  需求：每条功能需求必须含量化验收标准（验证前置方法论红线）
  Benchmark：必须含 high_frequency/edge/adversarial 三类；
             对抗样例的预期输出必须是安全拒绝（含「无法/不能/请通过正规」类表述）
  行业：industry/aliases 非空，便于自动匹配
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

REQUIRED_TOP = ["key", "industry", "name", "research_hints", "requirement_template", "benchmark_seed"]
REQUIRED_HINTS = ["business_nodes", "pain_points", "data_assets"]
REQUIRED_CASE_FIELDS = ["id", "input", "expected_output", "category"]
CATEGORIES = {"high_frequency", "edge", "adversarial"}
SAFETY_MARKERS = ("无法", "不能", "不得", "请通过正规", "违反", "拒绝")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_pack(data: dict) -> ValidationResult:
    """校验单个模板包 dict"""
    r = ValidationResult(ok=True)

    # 1) 顶层结构
    for k in REQUIRED_TOP:
        if k not in data or data[k] in (None, "", [], {}):
            r.error(f"缺少必填字段或为空: {k}")
    if r.errors:
        r.ok = False
        return r

    if not isinstance(data["key"], str) or not data["key"].replace("-", "").replace("_", "").isalnum():
        r.error("key 应为小写字母/数字/连字符（如 manufacturing）")
    if not data.get("aliases"):
        r.warn("建议提供 aliases（行业别名，中英文，提升自动匹配率）")

    # 2) research_hints
    hints = data.get("research_hints") or {}
    for k in REQUIRED_HINTS:
        if k not in hints:
            r.error(f"research_hints 缺少: {k}")
    if hints.get("compliance"):
        pass  # 金融/政务类强烈建议，但不强制
    else:
        r.warn("合规行业（金融/政务/医疗）建议提供 research_hints.compliance")

    # 3) 需求模板：量化验收标准红线
    reqs = data.get("requirement_template") or []
    if len(reqs) < 3:
        r.warn("requirement_template 建议 ≥3 条（覆盖核心场景）")
    for req in reqs:
        rid = req.get("id", "?")
        if not req.get("acceptance_criteria"):
            r.error(f"需求 {rid} 缺少 acceptance_criteria（验证前置红线：所有需求必须量化验收）")
        else:
            ac = str(req["acceptance_criteria"])
            has_quant = any(ch.isdigit() for ch in ac) or any(w in ac for w in ("率", "秒", "分钟", "倍", "%"))
            if not has_quant:
                r.error(f"需求 {rid} 的验收标准未量化（应含数字/比例/时限）: {ac}")
        if req.get("priority") not in ("P0", "P1", "P2"):
            r.error(f"需求 {rid} priority 非法: {req.get('priority')}")

    # 4) Benchmark 种子
    cases = data.get("benchmark_seed") or []
    if len(cases) < 3:
        r.error("benchmark_seed 至少 3 条")
    cats = {c.get("category") for c in cases}
    missing_cats = CATEGORIES - cats
    if missing_cats:
        r.error(f"benchmark_seed 缺少类别: {missing_cats}（三类必须齐备）")
    ids = [c.get("id") for c in cases]
    if len(ids) != len(set(ids)):
        r.error("benchmark_seed 存在重复 id")
    for c in cases:
        for f in REQUIRED_CASE_FIELDS:
            if not c.get(f):
                r.error(f"测试用例 {c.get('id', '?')} 缺少字段: {f}")
        if c.get("category") == "adversarial":
            expected = str(c.get("expected_output", ""))
            if not any(m in expected for m in SAFETY_MARKERS):
                r.error(f"对抗用例 {c.get('id')} 预期输出必须为安全拒绝（含 {'/'.join(SAFETY_MARKERS[:3])} 类表述）")

    r.ok = not r.errors
    return r


def validate_file(path: str) -> ValidationResult:
    if not os.path.exists(path):
        v = ValidationResult(ok=False)
        v.error(f"文件不存在: {path}")
        return v
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        v = ValidationResult(ok=False)
        v.error(f"JSON 解析失败: {e}")
        return v
    return validate_pack(data)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        # 无参数：校验全部内置包
        import glob

        packs = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "packs", "*.json")))
    else:
        packs = argv

    all_ok = True
    for path in packs:
        result = validate_file(path)
        name = os.path.basename(path)
        if result.ok:
            print(f"✅ {name} 通过")
            for w in result.warnings:
                print(f"   ⚠️ {w}")
        else:
            all_ok = False
            print(f"❌ {name} 未通过：")
            for e in result.errors:
                print(f"   - {e}")
            for w in result.warnings:
                print(f"   ⚠️ {w}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
