"""
知识库工具 - 基于LightRAG知识图谱RAG
MVP阶段使用模拟，生产环境调用LightRAG + Qdrant
"""
from __future__ import annotations

from typing import Any, Optional

from ..config import get_settings


class KnowledgeBaseTool:
    """知识库工具：文档入库、知识图谱构建、双层检索"""

    NAME = "knowledge_base"
    DESCRIPTION = "构建和查询LightRAG知识图谱知识库，支持实体关系级检索"

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.settings = get_settings()
        self._kbs: dict[str, dict] = {}  # kb_id -> kb_info
        self._qdrant_client = None  # 延迟初始化
        self._embedding_model = None  # 延迟初始化
        self._documents: dict[str, list[dict]] = {}  # kb_id -> 文档列表（mock模式）

    async def create(self, kb_name: str, config: Optional[dict] = None) -> dict:
        """创建知识库"""
        kb_id = f"kb_{self.project_id}_{kb_name}"
        kb_info = {
            "kb_id": kb_id,
            "kb_name": kb_name,
            "provider": self.settings.kb_provider,
            "status": "created",
            "document_count": 0,
            "entity_count": 0,
            "relation_count": 0,
            "config": config or {},
            "created_at": __import__("time").time(),
        }
        self._kbs[kb_id] = kb_info
        return kb_info

    def _get_qdrant_client(self):
        """延迟初始化Qdrant客户端"""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient
                self._qdrant_client = QdrantClient(
                    host=self.settings.qdrant_host,
                    port=self.settings.qdrant_port,
                    api_key=self.settings.qdrant_api_key or None,
                )
            except ImportError:
                print("[KB] qdrant-client未安装，降级到mock模式。安装: pip install qdrant-client")
                self._qdrant_client = "mock"
            except Exception as e:
                print(f"[KB] Qdrant连接失败，降级到mock模式: {e}")
                self._qdrant_client = "mock"
        return self._qdrant_client if self._qdrant_client != "mock" else None

    def _get_embedding_model(self):
        """延迟初始化Embedding模型"""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer(self.settings.kb_embedding_model)
            except ImportError:
                print("[KB] sentence-transformers未安装，使用模拟向量。安装: pip install sentence-transformers")
                self._embedding_model = "mock"
            except Exception as e:
                print(f"[KB] Embedding模型加载失败，使用模拟向量: {e}")
                self._embedding_model = "mock"
        return self._embedding_model if self._embedding_model != "mock" else None

    def _get_embedding(self, text: str) -> list[float]:
        """获取文本向量"""
        model = self._get_embedding_model()
        if model:
            return model.encode(text).tolist()
        # mock：返回固定维度的随机向量（基于文本hash保证一致性）
        import hashlib
        import random
        h = int(hashlib.md5(text.encode()).hexdigest(), 16)
        rng = random.Random(h)
        dim = self.settings.kb_embedding_dim
        return [rng.uniform(-1, 1) for _ in range(dim)]

    def _chunk_text(self, text: str) -> list[str]:
        """文本分块"""
        chunk_size = self.settings.kb_chunk_size
        overlap = self.settings.kb_chunk_overlap
        chunks = []
        words = text.split()
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
            i += chunk_size - overlap
        return chunks if chunks else [text]

    async def add_documents(self, kb_id: str, documents: list[dict]) -> dict:
        """
        添加文档并构建知识图谱
        documents: [{"content": "...", "filename": "...", "metadata": {...}}]
        """
        if kb_id not in self._kbs:
            return {"success": False, "error": f"知识库不存在: {kb_id}"}

        kb = self._kbs[kb_id]
        entities_added = 0
        relations_added = 0
        chunks_added = 0

        # 真实模式：使用Qdrant存储向量
        qdrant = self._get_qdrant_client() if self.settings.kb_provider in ("lightrag", "qdrant", "basic") else None

        for doc in documents:
            content = doc.get("content", "")
            filename = doc.get("filename", "unknown")

            # 实体关系抽取
            entities = self._extract_entities(content)
            entities_added += len(entities)
            relations_added += len(entities) // 2

            # 文本分块并向量化
            chunks = self._chunk_text(content)
            for i, chunk in enumerate(chunks):
                vector = self._get_embedding(chunk)
                chunks_added += 1

                if qdrant:
                    try:
                        from qdrant_client.models import PointStruct
                        qdrant.upsert(
                            collection_name=kb_id,
                            points=[PointStruct(
                                id=hash(f"{kb_id}_{filename}_{i}") % (2**32),
                                vector=vector,
                                payload={"text": chunk, "filename": filename, "chunk_index": i},
                            )],
                        )
                    except Exception as e:
                        print(f"[KB] Qdrant存储失败: {e}")

            # 保存文档原文（mock模式用）
            if kb_id not in self._documents:
                self._documents[kb_id] = []
            self._documents[kb_id].append({"content": content, "filename": filename})

        # 确保Qdrant集合存在
        if qdrant:
            try:
                from qdrant_client.models import VectorParams, Distance
                collections = [c.name for c in qdrant.get_collections().collections]
                if kb_id not in collections:
                    qdrant.create_collection(
                        collection_name=kb_id,
                        vectors_config=VectorParams(size=self.settings.kb_embedding_dim, distance=Distance.COSINE),
                    )
            except Exception as e:
                print(f"[KB] Qdrant集合创建失败: {e}")

        kb["document_count"] += len(documents)
        kb["entity_count"] += entities_added
        kb["relation_count"] += relations_added
        kb["chunk_count"] = kb.get("chunk_count", 0) + chunks_added
        kb["status"] = "ready"

        return {
            "success": True,
            "kb_id": kb_id,
            "documents_added": len(documents),
            "chunks_added": chunks_added,
            "entities_added": entities_added,
            "relations_added": relations_added,
            "total_documents": kb["document_count"],
            "total_entities": kb["entity_count"],
        }

    async def query(self, kb_id: str, question: str, top_k: int = 5) -> dict:
        """
        双层检索：关键词级 + 实体关系级
        返回: {"answers": [...], "sources": [...], "entities_matched": [...]}
        """
        if kb_id not in self._kbs:
            return {"success": False, "error": f"知识库不存在: {kb_id}"}

        kb = self._kbs[kb_id]

        # 真实模式：使用Qdrant向量检索
        qdrant = self._get_qdrant_client() if self.settings.kb_provider in ("lightrag", "qdrant", "basic") else None

        if qdrant:
            try:
                query_vector = self._get_embedding(question)
                search_results = qdrant.search(
                    collection_name=kb_id,
                    query_vector=query_vector,
                    limit=top_k,
                )
                answers = [
                    {
                        "content": hit.payload.get("text", ""),
                        "score": hit.score,
                        "source": hit.payload.get("filename", "unknown"),
                    }
                    for hit in search_results
                ]
                retrieval_mode = "vector_semantic"
            except Exception as e:
                print(f"[KB] Qdrant检索失败，降级到mock: {e}")
                answers = self._mock_query(question, top_k)
                retrieval_mode = "mock_fallback"
        else:
            answers = self._mock_query(question, top_k)
            retrieval_mode = "mock"

        return {
            "success": True,
            "kb_id": kb_id,
            "question": question,
            "answers": answers,
            "sources": [a["source"] for a in answers],
            "entities_matched": ["业务流程", "审核标准"],
            "retrieval_mode": retrieval_mode,
        }

    def _mock_query(self, question: str, top_k: int) -> list[dict]:
        """Mock检索结果"""
        return [
            {
                "content": f"基于知识库检索，关于'{question}'的回答：根据业务规范，相关流程需要经过受理、审核、处理三个环节。",
                "score": 0.88,
                "source": "业务操作手册第2章",
            },
            {
                "content": f"补充说明：{question}涉及的审核标准包括资料完整性和合规性两项，具体要求见规范第3.2条。",
                "score": 0.76,
                "source": "审核标准说明",
            },
        ][:top_k]

    async def get_stats(self, kb_id: str) -> dict:
        """获取知识库统计"""
        if kb_id not in self._kbs:
            return {"success": False, "error": f"知识库不存在: {kb_id}"}
        return {"success": True, **self._kbs[kb_id]}

    def _extract_entities(self, content: str) -> list[str]:
        """从内容中抽取实体（模拟）"""
        entity_keywords = ["流程", "审核", "标准", "系统", "客户", "业务", "规则", "模块", "服务", "数据"]
        found = []
        for kw in entity_keywords:
            if kw in content:
                found.append(kw)
        return found
