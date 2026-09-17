"""标题感知切块器——Embedded 参考实现内部组件（设计见 13 号 §3.1 前期处理管线）。

v1.2 契约下切块主权归知识库侧：引擎主流程推整篇文档；
本模块仅供 ① EmbeddedKnowledgeGateway 内部（文档级 ingest → 切块 → FTS）
        ② 附录 A 降级模式的对照实现使用。

规则：
- 按空行分段；标题行（Markdown # 或 数字编号）开启新块并滚动 title_path
- 目标块长 ~380 字（300-500 区间中值）：短段向下合并；超长段按句读边界二次切分
- 保留 (chunk_index, start_at, end_at) 字符偏移（溯源坐标，规格 §3.2 五字段之二）
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TARGET_LEN = 380
MAX_LEN = 520

# Markdown 标题 或 "1."/"1.2、"/"第三章" 式编号行
_HEADER_RE = re.compile(r"^(#{1,6}\s+\S|\d+(?:\.\d+)*[、.．\s]\s*\S|第[一二三四五六七八九十百]+[章节篇][^\n]{0,30}$)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


@dataclass
class RawChunk:
    content: str
    chunk_index: int
    start_at: int
    end_at: int
    title_path: str


def _paragraphs(text: str) -> list[tuple[str, int, int]]:
    """切分段落，返回 (段落文本, 起始偏移, 结束偏移)；偏移基于原文（含换行归属段落）"""
    result: list[tuple[str, int, int]] = []
    start = 0
    for raw in re.split(r"\n\s*\n", text):
        if not raw.strip():
            continue
        # 定位该段在原文中的真实起点（跳过前导空白）
        offset = text.find(raw, start)
        result.append((raw.strip(), offset, offset + len(raw)))
        start = offset + len(raw)
    if not result and text.strip():
        result.append((text.strip(), 0, len(text)))
    return result


def _split_long(text: str, base: int) -> list[tuple[str, int, int]]:
    """超长段落按句读边界二次切分（保偏移）"""
    sentences = [(m, base + text.find(m)) for m in _SENTENCE_SPLIT_RE.split(text) if m.strip()]
    out: list[tuple[str, int, int]] = []
    buf, buf_start = "", None
    for sent, off in sentences:
        if buf_start is None:
            buf_start = off
        if len(buf) + len(sent) > MAX_LEN and buf:
            out.append((buf, buf_start, buf_start + len(buf)))
            buf, buf_start = sent, off
        else:
            buf += sent
    if buf:
        out.append((buf, buf_start, buf_start + len(buf)))
    return out or [(text, base, base + len(text))]


def chunk_text(content: str, target_len: int = TARGET_LEN, max_len: int = MAX_LEN) -> list[RawChunk]:
    """标题感知切块；返回带字符偏移与 title_path 的块序列。"""
    chunks: list[RawChunk] = []
    title_parts: list[str] = []
    buf, buf_start = "", None

    def flush() -> None:
        nonlocal buf, buf_start
        if buf.strip():
            chunks.append(
                RawChunk(
                    content=buf.strip(),
                    chunk_index=len(chunks),
                    start_at=buf_start or 0,
                    end_at=(buf_start or 0) + len(buf),
                    title_path=">".join(title_parts),
                )
            )
        buf, buf_start = "", None

    for para, off, _end in _paragraphs(content):
        header = _HEADER_RE.match(para)
        if header:
            flush()
            title = para.lstrip("#").strip().rstrip("。") or para.strip()
            title_parts = title_parts[-2:] + [title[:40]]
        candidate = para if not buf else buf + "\n" + para
        if len(candidate) > max_len:
            flush()
            for piece, p_off, _pe in _split_long(para, off):
                if len(buf) + len(piece) > max_len and buf:
                    flush()
                buf = piece if not buf else buf + "\n" + piece
                if buf_start is None:
                    buf_start = p_off
            continue
        buf = candidate
        if buf_start is None:
            buf_start = off
        if len(buf) >= target_len:
            flush()
    flush()
    return chunks
