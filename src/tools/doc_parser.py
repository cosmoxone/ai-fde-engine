"""
文档解析工具 - 基于Marker v2 / Docling
MVP阶段使用模拟解析，生产环境调用Marker v2 GPU加速
"""

from __future__ import annotations

import os
from typing import Any, Optional

from ..config import get_settings


class DocParserTool:
    """文档解析工具：支持PDF/DOCX/PPTX/TXT/图片，输出结构化JSON"""

    NAME = "doc_parser"
    DESCRIPTION = "解析业务文档，提取结构化内容（段落、表格、标题、图片）"

    def __init__(self):
        self.settings = get_settings()
        self.provider = self.settings.doc_parser_provider

    async def parse(self, file_path: str, options: Optional[dict] = None) -> dict[str, Any]:
        """
        解析单个文档
        返回: {
            "filename": str,
            "file_type": str,
            "page_count": int,
            "content": str,           # 纯文本内容
            "structured": [...],      # 结构化块列表
            "tables": [...],          # 表格列表
            "metadata": {...},
            "parse_time_seconds": float,
        }
        """
        options = options or {}
        import time

        start = time.time()

        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}

        filename = os.path.basename(file_path)
        file_type = os.path.splitext(filename)[1].lower().lstrip(".")

        # 根据provider选择解析方式
        if self.provider == "docling":
            result = await self._parse_with_docling(file_path, filename, file_type)
        elif self.provider == "marker":
            result = await self._parse_with_marker(file_path, filename, file_type)
        elif self.provider == "hybrid":
            # 混合模式：PDF用Marker，其他用Docling
            if file_type == "pdf":
                result = await self._parse_with_marker(file_path, filename, file_type)
            else:
                result = await self._parse_with_docling(file_path, filename, file_type)
        else:
            # mock模式
            result = self._mock_parse(file_path, filename, file_type)

        result["parse_time_seconds"] = round(time.time() - start, 2)
        result["provider"] = self.provider
        return result

    async def parse_batch(self, file_paths: list[str], options: Optional[dict] = None) -> list[dict]:
        """批量解析文档"""
        results = []
        batch_size = self.settings.doc_parser_batch_size
        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i : i + batch_size]
            for fp in batch:
                result = await self.parse(fp, options)
                results.append(result)
        return results

    async def _parse_with_docling(self, file_path: str, filename: str, file_type: str) -> dict:
        """
        使用Docling解析文档（真实实现）
        安装: pip install docling
        Docling支持PDF/DOCX/PPTX/图片/HTML，输出结构化文档
        """
        try:
            from docling.document_converter import DocumentConverter

            # 初始化转换器（首次调用会下载模型）
            converter = DocumentConverter()

            # 执行转换
            conv_result = converter.convert(file_path)
            doc = conv_result.document

            # 提取纯文本
            content = doc.export_to_text()

            # 提取结构化块
            structured = []
            for item in doc.iterate_items():
                block = {
                    "type": item.__class__.__name__.lower(),
                    "text": item.text if hasattr(item, "text") else str(item),
                    "level": getattr(item, "level", 0),
                }
                structured.append(block)

            # 提取表格
            tables = []
            for table in doc.tables:
                tables.append(
                    {
                        "caption": table.caption,
                        "rows": len(table.data) if hasattr(table, "data") else 0,
                        "content": table.export_to_text() if hasattr(table, "export_to_text") else str(table),
                    }
                )

            return {
                "success": True,
                "filename": filename,
                "file_type": file_type,
                "page_count": len(doc.pages) if hasattr(doc, "pages") else 0,
                "content": content,
                "structured": structured,
                "tables": tables,
                "metadata": {
                    "docling_version": "2.x",
                    "input_format": file_type,
                },
            }
        except ImportError:
            # Docling未安装，降级到mock
            print("[DocParser] Docling未安装，降级到mock模式。安装: pip install docling")
            return self._mock_parse(file_path, filename, file_type)
        except Exception as e:
            return {"success": False, "error": f"Docling解析失败: {type(e).__name__}: {str(e)}"}

    async def _parse_with_marker(self, file_path: str, filename: str, file_type: str) -> dict:
        """
        使用Marker v2解析PDF文档（真实实现）
        安装: pip install marker-pdf
        Marker v2 GPU加速可达7.4页/秒，总分76.0超Docling
        适合大批量PDF文档解析
        """
        try:
            from marker.config.parser import ConfigParser
            from marker.converters.pdf import PdfConverter
            from marker.output import text_from_rendered

            # 配置
            config_parser = ConfigParser(
                {
                    "output_format": "markdown",
                    "use_gpu": self.settings.doc_parser_marker_gpu,
                    "language": self.settings.doc_parser_language,
                }
            )
            config = config_parser.generate_config()

            # 执行转换
            converter = PdfConverter(config=config)
            rendered = converter(file_path)
            content, metadata = text_from_rendered(rendered)

            # 结构化（Marker输出markdown，简单解析标题）
            structured = []
            for line in content.split("\n"):
                if line.startswith("#"):
                    level = len(line) - len(line.lstrip("#"))
                    structured.append({"type": "heading", "text": line.lstrip("# ").strip(), "level": level})
                elif line.strip():
                    structured.append({"type": "paragraph", "text": line.strip(), "level": 0})

            return {
                "success": True,
                "filename": filename,
                "file_type": file_type,
                "page_count": metadata.get("page_count", 0),
                "content": content,
                "structured": structured,
                "tables": [],
                "metadata": {
                    "marker_version": "2.x",
                    "gpu_used": self.settings.doc_parser_marker_gpu,
                    "raw_metadata": metadata,
                },
            }
        except ImportError:
            print("[DocParser] Marker未安装，降级到mock模式。安装: pip install marker-pdf")
            return self._mock_parse(file_path, filename, file_type)
        except Exception as e:
            return {"success": False, "error": f"Marker解析失败: {type(e).__name__}: {str(e)}"}

    def _mock_parse(self, file_path: str, filename: str, file_type: str) -> dict:
        """MVP模拟解析结果"""
        # 尝试读取文本内容
        content = ""
        try:
            if file_type in ("txt", "md", "csv"):
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            else:
                # PDF/DOCX等模拟内容
                content = f"[模拟解析] {filename}\n\n本文档包含业务流程说明、操作规范和历史案例。\n\n1. 业务受理流程\n客户提交申请后，系统自动登记基本信息，转审核环节。\n\n2. 审核标准\n资料完整性：必填字段不得为空。\n合规性：符合业务规范第3.2条要求。\n\n3. 常见问题\nQ: 资料缺失怎么办？A: 系统自动通知客户补充。\nQ: 审核不通过如何申诉？A: 提交申诉材料，3个工作日内回复。"
        except Exception as e:
            content = f"[解析失败] {e}"

        # 结构化块
        structured = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if line.startswith(("#", "1.", "2.", "3.", "4.", "5.")) or (
                len(line) < 30 and line.endswith(("流程", "标准", "问题"))
            ):
                block_type = "heading"
            elif line.startswith(("Q:", "A:")):
                block_type = "qa"
            else:
                block_type = "paragraph"
            structured.append({"id": f"B{i}", "type": block_type, "content": line, "page": 1})

        return {
            "success": True,
            "filename": filename,
            "file_type": file_type,
            "page_count": max(1, content.count("\n") // 40),
            "content": content,
            "structured": structured,
            "tables": [],  # MVP模拟无表格
            "metadata": {"parser_version": "mock-1.0", "language": self.settings.doc_parser_language},
        }
