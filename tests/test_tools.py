"""
工具模块测试
"""

import os

import pytest

from src.tools.benchmark import BenchmarkTool
from src.tools.code_gen import CodeGenTool
from src.tools.data_explorer import DataExplorerTool
from src.tools.doc_parser import DocParserTool
from src.tools.knowledge_base import KnowledgeBaseTool


@pytest.fixture
def sample_txt_file(tmp_path):
    """创建测试文本文件"""
    file_path = tmp_path / "test_doc.txt"
    file_path.write_text(
        """业务操作手册

1. 业务受理流程
客户提交申请后，系统自动登记基本信息，转审核环节。

2. 审核标准
资料完整性：必填字段不得为空。
合规性：符合业务规范第3.2条要求。

3. 常见问题
Q: 资料缺失怎么办？
A: 系统自动通知客户补充。
Q: 审核不通过如何申诉？
A: 提交申诉材料，3个工作日内回复。
""",
        encoding="utf-8",
    )
    return str(file_path)


class TestDocParserTool:
    """文档解析工具测试"""

    def test_tool_name(self):
        assert DocParserTool.NAME == "doc_parser"

    @pytest.mark.asyncio
    async def test_parse_txt(self, sample_txt_file):
        tool = DocParserTool()
        result = await tool.parse(sample_txt_file)
        assert result["success"] is True
        assert result["filename"] == "test_doc.txt"
        assert result["file_type"] == "txt"
        assert "业务受理流程" in result["content"]
        assert len(result["structured"]) > 0
        assert "parse_time_seconds" in result

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self):
        tool = DocParserTool()
        result = await tool.parse("/nonexistent/file.pdf")
        assert result["success"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_parse_batch(self, sample_txt_file, tmp_path):
        tool = DocParserTool()
        file2 = tmp_path / "doc2.txt"
        file2.write_text("第二个文档内容", encoding="utf-8")
        results = await tool.parse_batch([sample_txt_file, str(file2)])
        assert len(results) == 2
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_structured_blocks_have_types(self, sample_txt_file):
        tool = DocParserTool()
        result = await tool.parse(sample_txt_file)
        block_types = set(b["type"] for b in result["structured"])
        assert "heading" in block_types or "paragraph" in block_types


class TestKnowledgeBaseTool:
    """知识库工具测试"""

    @pytest.fixture
    def kb_tool(self, tmp_path):
        return KnowledgeBaseTool("test_project")

    @pytest.mark.asyncio
    async def test_create_kb(self, kb_tool):
        result = await kb_tool.create("test_kb")
        assert result["kb_name"] == "test_kb"
        assert result["status"] == "created"
        assert result["document_count"] == 0

    @pytest.mark.asyncio
    async def test_add_documents(self, kb_tool):
        await kb_tool.create("test_kb")
        result = await kb_tool.add_documents(
            "kb_test_project_test_kb",
            [
                {"content": "业务流程包括受理、审核、处理", "filename": "doc1.pdf"},
                {"content": "审核标准包括完整性和合规性", "filename": "doc2.pdf"},
            ],
        )
        assert result["success"] is True
        assert result["documents_added"] == 2
        assert result["entities_added"] > 0

    @pytest.mark.asyncio
    async def test_query(self, kb_tool):
        kb_id = "kb_test_project_test_kb"
        await kb_tool.create("test_kb")
        await kb_tool.add_documents(kb_id, [{"content": "业务流程包括受理、审核、处理三个环节"}])
        result = await kb_tool.query(kb_id, "业务流程有哪些环节？")
        assert result["success"] is True
        assert len(result["answers"]) > 0
        assert "retrieval_mode" in result

    @pytest.mark.asyncio
    async def test_query_nonexistent_kb(self, kb_tool):
        result = await kb_tool.query("nonexistent_kb", "test")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_get_stats(self, kb_tool):
        await kb_tool.create("test_kb")
        result = await kb_tool.get_stats("kb_test_project_test_kb")
        assert result["success"] is True
        assert result["document_count"] == 0


class TestBenchmarkTool:
    """Benchmark工具测试"""

    @pytest.fixture
    def bm_tool(self, tmp_path):
        return BenchmarkTool("test_project")

    @pytest.mark.asyncio
    async def test_generate(self, bm_tool):
        result = await bm_tool.generate([{"content": "业务文档内容", "filename": "doc.pdf"}], {"case_count": 20})
        assert result["case_count"] == 20
        assert len(result["test_cases"]) == 20
        assert "high_frequency" in result["category_distribution"]
        assert "edge" in result["category_distribution"]
        assert "adversarial" in result["category_distribution"]

    @pytest.mark.asyncio
    async def test_test_cases_have_required_fields(self, bm_tool):
        result = await bm_tool.generate([{"content": "test"}], {"case_count": 10})
        for tc in result["test_cases"]:
            assert "id" in tc
            assert "input" in tc
            assert "expected_output" in tc
            assert "category" in tc
            assert "difficulty" in tc

    @pytest.mark.asyncio
    async def test_category_distribution(self, bm_tool):
        result = await bm_tool.generate([{"content": "test"}], {"case_count": 100})
        dist = result["category_distribution"]
        assert dist["high_frequency"] + dist["edge"] + dist["adversarial"] == 100

    @pytest.mark.asyncio
    async def test_run_evaluation(self, bm_tool):
        bm = await bm_tool.generate([{"content": "test"}], {"case_count": 10})
        result = await bm_tool.run_evaluation(bm["benchmark_id"])
        assert result["success"] is True
        assert result["total_cases"] == 10
        assert "accuracy" in result
        assert "hallucination_rate" in result
        assert "gate_passed" in result
        assert "by_category" in result

    @pytest.mark.asyncio
    async def test_get_report(self, bm_tool):
        bm = await bm_tool.generate([{"content": "test"}], {"case_count": 5})
        eval_result = await bm_tool.run_evaluation(bm["benchmark_id"])
        report = await bm_tool.get_report(bm["benchmark_id"], eval_result)
        assert "Benchmark评测报告" in report
        assert "准确率" in report
        assert "幻觉率" in report


class TestCodeGenTool:
    """代码生成工具测试"""

    @pytest.fixture
    def code_tool(self, tmp_path):
        os.environ["OPENHANDS_WORKSPACE_BASE"] = str(tmp_path)
        return CodeGenTool("test_project")

    @pytest.mark.asyncio
    async def test_generate_project(self, code_tool):
        result = await code_tool.generate_project(
            requirements=[{"id": "R1", "title": "测试功能"}],
            tech_stack={"frontend": "React", "backend": "FastAPI"},
            project_name="test_proj",
        )
        assert result["success"] is True
        assert result["project_name"] == "test_proj"
        assert result["files_generated"] > 0
        assert os.path.exists(result["project_path"])

    @pytest.mark.asyncio
    async def test_generated_files_exist(self, code_tool):
        result = await code_tool.generate_project(requirements=[], tech_stack={}, project_name="file_test")
        project_path = result["project_path"]
        assert os.path.exists(os.path.join(project_path, "app", "main.py"))
        assert os.path.exists(os.path.join(project_path, "requirements.txt"))
        assert os.path.exists(os.path.join(project_path, "README.md"))

    @pytest.mark.asyncio
    async def test_fix_issue(self, code_tool):
        result = await code_tool.fix_issue("/tmp/repo", "修复空指针异常")
        assert result["success"] is True
        assert "files_modified" in result
        assert result["tests_passed"] is True

    @pytest.mark.asyncio
    async def test_run_tests(self, code_tool):
        result = await code_tool.run_tests("/tmp/repo")
        assert result["success"] is True
        assert "total_tests" in result
        assert "passed" in result
        assert "coverage" in result


class TestDataExplorerTool:
    """数据探查工具测试"""

    @pytest.fixture
    def explorer(self):
        return DataExplorerTool()

    @pytest.mark.asyncio
    async def test_connect(self, explorer):
        result = await explorer.connect("postgresql://user:pass@localhost:5432/db")
        assert result["success"] is True
        assert "connection_id" in result

    @pytest.mark.asyncio
    async def test_explore_schema(self, explorer):
        conn = await explorer.connect("postgresql://test")
        result = await explorer.explore_schema(conn["connection_id"])
        assert result["success"] is True
        assert result["table_count"] > 0
        assert len(result["tables"]) == 3
        for table in result["tables"]:
            assert "name" in table
            assert "columns" in table
            assert "row_count" in table

    @pytest.mark.asyncio
    async def test_assess_quality(self, explorer):
        conn = await explorer.connect("postgresql://test")
        result = await explorer.assess_quality(conn["connection_id"])
        assert result["success"] is True
        assert "overall_score" in result
        assert "dimensions" in result
        assert "issues" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_generate_access_plan(self, explorer):
        conn = await explorer.connect("postgresql://test")
        result = await explorer.generate_access_plan(conn["connection_id"])
        assert result["success"] is True
        assert "access_mode" in result
        assert "sync_strategy" in result
        assert "sensitive_columns" in result
        assert "security_measures" in result

    @pytest.mark.asyncio
    async def test_query_data(self, explorer):
        conn = await explorer.connect("postgresql://test")
        result = await explorer.query_data(conn["connection_id"], "SELECT * FROM orders LIMIT 5")
        assert result["success"] is True
        assert result["row_count"] == 5
        assert len(result["rows"]) == 5
        assert "columns" in result
