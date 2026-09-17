"""Dashboard 前端冒烟测试（v0.4：知识库 + 本体图谱两页面）。

只验证服务端交付的 HTML 完整性（导航/页面容器/关键函数/mermaid 降级），
交互逻辑由后端 API 测试覆盖（test_knowledge_api / test_ontology）。
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c


class TestDashboardV04:
    def test_dashboard_served(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    def test_new_pages_present(self, client):
        html = client.get("/dashboard").text
        # 导航与页面容器
        assert 'data-page="knowledge"' in html and 'id="page-knowledge"' in html
        assert 'data-page="ontology"' in html and 'id="page-ontology"' in html
        # 知识库页关键元素：检索/待确认队列/重建
        for token in ("kb-query", "kb-pending-queue", "kbRebuild", "kbConfirm", "kbReject", "kbSearch"):
            assert token in html, f"缺知识库元素: {token}"
        # 本体页关键元素：抽取/mermaid/实体管理
        for token in ("ontoExtract", "onto-mermaid", "ontoDeleteEntity", "ontoSearch", "renderOntoMermaid"):
            assert token in html, f"缺本体元素: {token}"

    def test_mermaid_fallback_logic(self, client):
        """离线降级：mermaid 未加载时显示源码（不白屏）。"""
        html = client.get("/dashboard").text
        assert "cdn.jsdelivr.net/npm/mermaid" in html, "应有 mermaid CDN 引用"
        assert "window.mermaid" in html and "离线模式" in html, "应有降级渲染分支"

    def test_version_bumped(self, client):
        assert "v0.4.0" in client.get("/dashboard").text
