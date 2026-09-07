"""
行业模板库测试（v0.1.2 B2）
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.templates import (
    BuiltinTemplateSource,
    build_research_context,
    get_template_source,
    match_template,
    reset_template_source,
)


class TestBuiltinPacks:
    def test_three_packs_loaded(self):
        keys = {p.key for p in BuiltinTemplateSource().list_packs()}
        assert keys == {"manufacturing", "finance", "government"}

    def test_pack_content_complete(self):
        pack = BuiltinTemplateSource().get_pack("manufacturing")
        assert pack.industry == "制造业"
        assert len(pack.requirement_template) >= 3
        assert len(pack.benchmark_seed) >= 3
        assert pack.research_hints.get("business_nodes")
        assert {c["category"] for c in pack.benchmark_seed} >= {"high_frequency", "adversarial"}
        # 每条需求都有验收标准（量化方法论一致性）
        for r in pack.requirement_template:
            assert r["acceptance_criteria"]

    def test_adversarial_seeds_refuse_unsafe(self):
        """对抗样例的预期输出必须是安全拒绝（方法论红线）"""
        for key in ("manufacturing", "finance", "government"):
            pack = BuiltinTemplateSource().get_pack(key)
            adv = [c for c in pack.benchmark_seed if c["category"] == "adversarial"]
            assert adv, f"{key} 缺对抗样例"
            for c in adv:
                assert any(w in c["expected_output"] for w in ("无法", "不能", "请通过正规", "违反"))


class TestMatchTemplate:
    def setup_method(self):
        reset_template_source()

    @pytest.mark.parametrize(
        "industry,expected",
        [
            ("制造业", "manufacturing"),
            ("manufacturing", "manufacturing"),
            ("汽车零部件制造", "manufacturing"),
            ("金融", "finance"),
            ("银行", "finance"),
            ("政务", "government"),
            ("12345热线", "government"),
            ("完全不相关的行业", None),
            ("", None),
        ],
    )
    def test_match(self, industry, expected):
        pack = match_template(industry)
        assert (pack.key if pack else None) == expected


class TestResearchContext:
    def test_build_context_contains_key_sections(self):
        pack = match_template("制造业")
        ctx = build_research_context(pack)
        assert "行业模板上下文" in ctx
        assert "IQC" in ctx
        assert "合规要求" in ctx


class TestTemplatesAPI:
    def test_list_templates(self, client: TestClient):
        resp = client.get("/api/v1/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["templates"]) == 3
        assert any(t["key"] == "manufacturing" and t["benchmark_seed_count"] >= 3 for t in data["templates"])


class TestInjectionIntegration:
    def test_research_uses_industry_context(self, client: TestClient):
        """制造业项目调研 → mock summary 出现行业节点（上下文参与分析）"""
        pid = client.post(
            "/api/v1/projects", json={"name": "行业注入验证", "client_name": "客户", "industry": "制造业"}
        ).json()["project"]["id"]
        tid = client.post(f"/api/v1/projects/{pid}/research/run", json={"client_requirements": "质检知识库"}).json()[
            "task_id"
        ]
        import time

        for _ in range(40):
            t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        # mock 分析包含输入内容预览 → 行业上下文应出现在 summary 资料概览中
        assert "IQC" in t["result"]["content"] or "来料检验" in t["result"]["content"]

    def test_benchmark_empty_docs_use_seed(self, client: TestClient):
        """无文档的制造业项目生成 Benchmark → 含行业种子用例"""
        pid = client.post(
            "/api/v1/projects", json={"name": "种子验证", "client_name": "客户", "industry": "制造业"}
        ).json()["project"]["id"]
        tid = client.post(f"/api/v1/projects/{pid}/benchmarks/generate", json={}).json()["task_id"]
        import time

        for _ in range(40):
            t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
            if t["status"] != "running":
                break
            time.sleep(0.05)
        assert t["status"] == "completed"
        bm = client.get(f"/api/v1/projects/{pid}/benchmarks").json()["benchmarks"][0]
        inputs = " ".join(str(c.get("input", "")) for c in bm["test_cases"])
        assert "MF-1023" in inputs or "让步" in inputs  # 制造业种子样例特征


class TestTemplateSourceExtension:
    def test_plugin_can_replace_source(self):
        """TE 订阅源替换内置源（A5 扩展点贯通）"""
        from src.extensions import PluginInfo, get_registry, reset_registry
        from src.templates import TemplateSource

        class RemoteSource(TemplateSource):
            def list_packs(self):
                pack = BuiltinTemplateSource().get_pack("finance")
                return [pack]

            def get_pack(self, key):
                return self.list_packs()[0] if key == "finance" else None

        reset_registry()
        reset_template_source()
        registry = get_registry()
        plugin = PluginInfo(name="team-edition", version="1.0.0", provider="team")
        plugin.hooks["template_source"] = RemoteSource()
        registry.register(plugin)

        assert {p.key for p in get_template_source().list_packs()} == {"finance"}
        reset_registry()
        reset_template_source()
        assert {p.key for p in get_template_source().list_packs()} == {
            "manufacturing",
            "finance",
            "government",
        }
