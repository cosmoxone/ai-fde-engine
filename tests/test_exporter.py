"""
交付物导出测试（v0.1.2 B1）
"""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.exporter import build_deliverables, export_zip


@pytest.fixture
def rich_project(client: TestClient) -> str:
    """跑完 调研→设计→Benchmark→夜间迭代 的完整项目"""
    pid = client.post(
        "/api/v1/projects", json={"name": "导出测试项目", "client_name": "测试客户", "industry": "制造业"}
    ).json()["project"]["id"]

    # 文档
    client.post(
        f"/api/v1/projects/{pid}/documents",
        files={"file": ("spec.md", "# 质检手册\n内容".encode("utf-8"), "text/markdown")},
    )

    # 调研（同步等待后台任务完成）
    tid = client.post(f"/api/v1/projects/{pid}/research/run", json={"client_requirements": "质检知识库"}).json()[
        "task_id"
    ]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        import time

        time.sleep(0.05)
    assert t["status"] == "completed", t

    # 设计
    tid = client.post(f"/api/v1/projects/{pid}/design/run", json={}).json()["task_id"]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        import time

        time.sleep(0.05)
    assert t["status"] == "completed", t

    # Benchmark
    tid = client.post(f"/api/v1/projects/{pid}/benchmarks/generate", json={}).json()["task_id"]
    for _ in range(40):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        import time

        time.sleep(0.05)

    # 夜间迭代
    tid = client.post(
        f"/api/v1/projects/{pid}/iteration/run",
        json={
            "badcases": [],
            "benchmark_cases": [{"input": "q", "expected_output": "a", "category": "high_frequency"}],
        },
    ).json()["task_id"]
    for _ in range(60):
        t = client.get(f"/api/v1/tasks/{tid}").json()["task"]
        if t["status"] != "running":
            break
        import time

        time.sleep(0.05)
    return pid


class TestBuildDeliverables:
    def test_full_project_has_six_items(self, rich_project):
        items = build_deliverables(rich_project)
        keys = [d.key for d in items]
        assert "01-项目概览" in keys
        assert "02-需求基线" in keys
        assert "03-方案设计" in keys
        assert "04-Benchmark测试集" in keys
        assert "05-迭代报告" in keys
        assert "06-评审记录" in keys

    def test_baseline_contains_acceptance(self, rich_project):
        md = {d.key: d.markdown for d in build_deliverables(rich_project)}
        baseline = md["02-需求基线"]
        assert "验收标准" in baseline
        assert "功能需求" in baseline
        assert "|" in baseline  # 表格

    def test_missing_project_raises(self):
        with pytest.raises(ValueError, match="项目不存在"):
            build_deliverables("nope")

    def test_empty_project_only_overview(self, client):
        pid = client.post("/api/v1/projects", json={"name": "空项目"}).json()["project"]["id"]
        items = build_deliverables(pid)
        keys = [d.key for d in items]
        assert keys == ["01-项目概览", "07-复盘报告"]  # v0.2.0起复盘零数据也生成


class TestExportZip:
    def test_zip_md(self, rich_project):
        filename, content = export_zip(rich_project, fmt="md")
        assert filename.endswith(".zip")
        zf = zipfile.ZipFile(io.BytesIO(content))
        names = zf.namelist()
        assert "README.md" in names
        assert "02-需求基线.md" in names
        body = zf.read("02-需求基线.md").decode("utf-8")
        assert "功能需求" in body

    def test_zip_docx(self, rich_project):
        """python-docx 已安装时导出 docx 文件（PK 头校验）"""
        filename, content = export_zip(rich_project, fmt="docx")
        zf = zipfile.ZipFile(io.BytesIO(content))
        names = zf.namelist()
        assert "02-需求基线.docx" in names
        docx_bytes = zf.read("02-需求基线.docx")
        assert docx_bytes[:2] == b"PK"  # docx 即 zip
        inner = zipfile.ZipFile(io.BytesIO(docx_bytes))
        assert "word/document.xml" in inner.namelist()


class TestDocxRenderer:
    def test_markdown_to_docx(self):
        from src.exporter.docx_renderer import markdown_to_docx

        md = "# 标题\n\n段落**加粗**文本\n\n- 列表项A\n- 列表项B\n\n| 列1 | 列2 |\n| --- | --- |\n| a | b |\n\n```python\nprint(1)\n```"
        data = markdown_to_docx("测试文档", md)
        assert data[:2] == b"PK"
        inner = zipfile.ZipFile(io.BytesIO(data))
        xml = inner.read("word/document.xml").decode("utf-8")
        assert "加粗" in xml
        assert "列表项A" in xml
        assert "print(1)" in xml

    def test_docx_import_error_message(self, monkeypatch):
        import builtins

        from src.exporter.docx_renderer import markdown_to_docx

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "docx":
                raise ImportError("no docx")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="python-docx"):
            markdown_to_docx("t", "# h")


class TestExportAPI:
    def test_export_list(self, rich_project, client):
        resp = client.get(f"/api/v1/projects/{rich_project}/export/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total"] >= 5
        assert any(i["key"] == "02-需求基线" for i in data["items"])

    def test_export_zip_md(self, rich_project, client):
        resp = client.get(f"/api/v1/projects/{rich_project}/export", params={"format": "md"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert "README.md" in zf.namelist()

    def test_export_zip_docx(self, rich_project, client):
        resp = client.get(f"/api/v1/projects/{rich_project}/export", params={"format": "docx"})
        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert "03-方案设计.docx" in zf.namelist()

    def test_export_single_item_markdown(self, rich_project, client):
        resp = client.get(f"/api/v1/projects/{rich_project}/export", params={"format": "md", "item": "02-需求基线"})
        assert resp.status_code == 200
        assert "功能需求" in resp.text

    def test_export_invalid_format(self, rich_project, client):
        resp = client.get(f"/api/v1/projects/{rich_project}/export", params={"format": "pdf"})
        assert resp.status_code == 400

    def test_export_404(self, client):
        assert client.get("/api/v1/projects/nope/export").status_code == 404
