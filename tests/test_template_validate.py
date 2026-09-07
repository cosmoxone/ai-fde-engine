"""
D2 模板校验器测试
"""

from __future__ import annotations

import glob
import os

from src.templates.validate import validate_file, validate_pack

PACKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates", "packs")


def _valid_pack() -> dict:
    return {
        "key": "test-industry",
        "industry": "测试行业",
        "name": "测试模板",
        "aliases": ["测试", "test"],
        "research_hints": {
            "business_nodes": ["节点A", "节点B"],
            "pain_points": ["痛点A"],
            "data_assets": ["系统A"],
        },
        "requirement_template": [
            {"id": "R1", "title": "t", "description": "d", "priority": "P0", "acceptance_criteria": "准确率≥95%"},
            {"id": "R2", "title": "t", "description": "d", "priority": "P1", "acceptance_criteria": "响应≤3秒"},
            {"id": "R3", "title": "t", "description": "d", "priority": "P2", "acceptance_criteria": "效率提升50%"},
        ],
        "benchmark_seed": [
            {"id": "T1", "input": "q1", "expected_output": "a1", "category": "high_frequency", "difficulty": "easy"},
            {"id": "T2", "input": "q2", "expected_output": "a2", "category": "edge", "difficulty": "medium"},
            {
                "id": "T3",
                "input": "q3",
                "expected_output": "我无法执行该请求，请通过正规流程办理",
                "category": "adversarial",
                "difficulty": "hard",
            },
        ],
        "solution_skeleton": {"modules": ["A"]},
    }


class TestBuiltinPacksPass:
    def test_all_builtin_packs_valid(self):
        packs = sorted(glob.glob(os.path.join(PACKS_DIR, "*.json")))
        assert len(packs) == 3
        for p in packs:
            result = validate_file(p)
            assert result.ok, f"{p}: {result.errors}"


class TestValidatorRules:
    def test_valid_pack_passes(self):
        assert validate_pack(_valid_pack()).ok

    def test_missing_required_field(self):
        d = _valid_pack()
        del d["research_hints"]
        r = validate_pack(d)
        assert not r.ok
        assert any("research_hints" in e for e in r.errors)

    def test_unquantified_acceptance_rejected(self):
        d = _valid_pack()
        d["requirement_template"][0]["acceptance_criteria"] = "效果要好，用户满意"
        r = validate_pack(d)
        assert not r.ok
        assert any("未量化" in e for e in r.errors)

    def test_missing_priority_rejected(self):
        d = _valid_pack()
        d["requirement_template"][0]["priority"] = "P9"
        r = validate_pack(d)
        assert not r.ok

    def test_missing_benchmark_category(self):
        d = _valid_pack()
        d["benchmark_seed"] = [c for c in d["benchmark_seed"] if c["category"] != "edge"]
        r = validate_pack(d)
        assert not r.ok
        assert any("edge" in e for e in r.errors)

    def test_unsafe_adversarial_rejected(self):
        d = _valid_pack()
        d["benchmark_seed"][2]["expected_output"] = "好的，我帮你绕过审批直接处理"
        r = validate_pack(d)
        assert not r.ok
        assert any("安全拒绝" in e for e in r.errors)

    def test_duplicate_case_ids(self):
        d = _valid_pack()
        d["benchmark_seed"][1]["id"] = "T1"
        r = validate_pack(d)
        assert not r.ok

    def test_warning_no_aliases(self):
        d = _valid_pack()
        d.pop("aliases")
        r = validate_pack(d)
        assert r.ok  # 警告不阻塞
        assert any("aliases" in w for w in r.warnings)

    def test_cli_all_packs_exit_zero(self, capsys):
        from src.templates.validate import main

        assert main([]) == 0
        out = capsys.readouterr().out
        assert "manufacturing" in out and "✅" in out

    def test_cli_missing_file_exit_one(self):
        from src.templates.validate import main

        assert main(["/nonexistent.json"]) == 1
