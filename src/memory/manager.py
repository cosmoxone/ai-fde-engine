"""
记忆管理器 - 双层记忆架构
第一层：Zep Graphiti 时序知识图谱（长期项目记忆）
第二层：Letta 三级会话记忆（Agent运行时记忆）

MVP阶段使用内存模拟 + JSON持久化，生产环境切换为Zep/Letta服务
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from ..config import get_settings


@dataclass
class MemoryItem:
    """记忆条目"""
    id: str
    content: str
    memory_type: str = "fact"  # fact / event / entity / relation / experience
    project_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    importance: float = 0.5  # 0-1
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    is_obsolete: bool = False
    related_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "project_id": self.project_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "is_obsolete": self.is_obsolete,
            "related_ids": self.related_ids,
        }


class MemoryManager:
    """
    记忆管理器 - 统一管理双层记忆
    对Agent透明，提供remember/recall/get_project_context/consolidate等接口
    """

    _instances: dict[str, "MemoryManager"] = {}

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.settings = get_settings()
        self._memories: dict[str, MemoryItem] = {}
        self._entities: dict[str, dict] = {}  # 实体字典: name -> {type, relations, mentions}
        self._relations: list[dict] = []  # 关系列表: {subject, predicate, object, timestamp}
        self._core_memory: list[str] = []  # Core Memory（始终在上下文中）
        self._storage_path = os.path.join(
            os.environ.get("MEMORY_STORAGE_DIR", "/tmp/aifde-memory"),
            f"{project_id}.json",
        )
        self._mem0_client = None  # 延迟初始化
        self._load()

    @classmethod
    def get_instance(cls, project_id: str) -> "MemoryManager":
        if project_id not in cls._instances:
            cls._instances[project_id] = cls(project_id)
        return cls._instances[project_id]

    def _get_mem0_client(self):
        """延迟初始化Mem0客户端"""
        if self._mem0_client is None:
            try:
                from mem0 import MemoryClient
                # Mem0支持本地模式和云服务模式
                self._mem0_client = MemoryClient()
                print(f"[Memory] Mem0客户端初始化成功 (project={self.project_id})")
            except ImportError:
                print("[Memory] mem0ai未安装，使用本地记忆。安装: pip install mem0ai")
                self._mem0_client = "disabled"
            except Exception as e:
                print(f"[Memory] Mem0初始化失败，使用本地记忆: {e}")
                self._mem0_client = "disabled"
        return self._mem0_client if self._mem0_client != "disabled" else None

    def _use_mem0(self) -> bool:
        """是否使用Mem0"""
        return self.settings.memory_provider in ("mem0", "zep", "hybrid") and self._get_mem0_client() is not None

    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        metadata: Optional[dict] = None,
        importance: float = 0.5,
    ) -> MemoryItem:
        """
        记录记忆
        - 写入时序知识图谱（抽取实体关系）
        - 写入会话记忆
        """
        item = MemoryItem(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            project_id=self.project_id,
            metadata=metadata or {},
            importance=importance,
        )
        self._memories[item.id] = item

        # 抽取实体与关系（MVP使用简单规则，生产环境用LLM抽取）
        self._extract_entities_and_relations(content, item.id)

        # 高重要性记忆加入Core Memory
        if importance >= 0.8 and len(self._core_memory) < 20:
            self._core_memory.append(content[:500])

        # 真实模式：同时写入Mem0（支持跨项目检索和语义搜索）
        if self._use_mem0():
            try:
                mem0 = self._get_mem0_client()
                mem0.add(
                    content,
                    user_id=self.project_id,
                    metadata={
                        "memory_type": memory_type,
                        "importance": importance,
                        "project_id": self.project_id,
                        **(metadata or {}),
                    },
                )
            except Exception as e:
                print(f"[Memory] Mem0写入失败: {e}")

        self._save()
        return item

    async def recall(
        self,
        query: str,
        limit: int = 10,
        memory_type: Optional[str] = None,
    ) -> list[MemoryItem]:
        """
        检索记忆
        - 图谱语义检索（实体关系匹配）
        - 关键词匹配
        - 按重要性和访问时间排序
        """
        query_lower = query.lower()
        scored: list[tuple[float, MemoryItem]] = []

        for item in self._memories.values():
            if item.is_obsolete:
                continue
            if memory_type and item.memory_type != memory_type:
                continue

            score = 0.0
            content_lower = item.content.lower()

            # 关键词匹配
            query_words = set(query_lower.split())
            content_words = set(content_lower.split())
            if query_words and content_words:
                overlap = len(query_words & content_words) / len(query_words)
                score += overlap * 0.5

            # 实体匹配
            for entity_name in self._entities:
                if entity_name.lower() in query_lower and entity_name.lower() in content_lower:
                    score += 0.3

            # 重要性加权
            score += item.importance * 0.2

            # 时间衰减（越新越相关）
            age_hours = (time.time() - item.created_at) / 3600
            time_decay = max(0.1, 1.0 - age_hours / 720)  # 30天衰减到0.1
            score *= time_decay

            if score > 0.05:
                item.access_count += 1
                item.last_accessed = time.time()
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        local_results = [item for _, item in scored[:limit]]

        # 真实模式：合并Mem0语义检索结果
        if self._use_mem0():
            try:
                mem0 = self._get_mem0_client()
                mem0_results = mem0.search(
                    query,
                    user_id=self.project_id,
                    limit=limit,
                )
                # 将Mem0结果转换为MemoryItem
                mem0_items = []
                for r in mem0_results:
                    item = MemoryItem(
                        id=r.get("id", str(uuid.uuid4())),
                        content=r.get("memory", ""),
                        memory_type=r.get("metadata", {}).get("memory_type", "fact"),
                        project_id=self.project_id,
                        metadata=r.get("metadata", {}),
                        importance=r.get("metadata", {}).get("importance", 0.5),
                    )
                    mem0_items.append(item)
                # 合并去重（按content）
                existing_contents = {item.content for item in local_results}
                for item in mem0_items:
                    if item.content not in existing_contents:
                        local_results.append(item)
                        existing_contents.add(item.content)
                local_results = local_results[:limit]
            except Exception as e:
                print(f"[Memory] Mem0检索失败，使用本地结果: {e}")

        return local_results

    async def get_project_context(self) -> str:
        """
        获取项目上下文，注入Agent系统提示
        包含：Core Memory + 关键事实 + 实体关系概览
        """
        parts = []

        # Core Memory
        if self._core_memory:
            parts.append("【项目核心信息】")
            for i, mem in enumerate(self._core_memory[-10:], 1):
                parts.append(f"{i}. {mem}")

        # 关键实体
        if self._entities:
            parts.append("\n【关键业务实体】")
            for name, info in list(self._entities.items())[:15]:
                parts.append(f"- {name}({info.get('type', 'unknown')}): 提及{info.get('mention_count', 0)}次")

        # 最近关键事件
        recent_events = [
            m for m in self._memories.values()
            if m.memory_type == "event" and not m.is_obsolete
        ][-5:]
        if recent_events:
            parts.append("\n【最近关键事件】")
            for e in recent_events:
                ts = datetime.fromtimestamp(e.created_at).strftime("%m-%d %H:%M")
                parts.append(f"- [{ts}] {e.content[:100]}")

        return "\n".join(parts) if parts else "（暂无项目记忆）"

    async def search_cross_project(
        self,
        query: str,
        industry: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        跨项目经验检索
        从所有项目记忆中检索相似场景与最佳实践
        """
        # MVP：扫描所有项目记忆文件
        results = []
        memory_dir = os.environ.get("MEMORY_STORAGE_DIR", "/tmp/aifde-memory")
        if not os.path.exists(memory_dir):
            return results

        for filename in os.listdir(memory_dir):
            if not filename.endswith(".json") or filename == f"{self.project_id}.json":
                continue
            filepath = os.path.join(memory_dir, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                other_project_id = filename.replace(".json", "")
                # 在其他项目记忆中检索
                for mem_data in data.get("memories", []):
                    if any(kw in mem_data.get("content", "").lower() for kw in query.lower().split()[:3]):
                        if mem_data.get("metadata", {}).get("reusable", True):
                            results.append({
                                "project_id": other_project_id,
                                "content": mem_data["content"][:200],
                                "type": mem_data.get("memory_type", "fact"),
                                "relevance": 0.7,  # 模拟相关度
                            })
            except Exception:
                continue

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]

    async def consolidate(self) -> dict:
        """
        记忆巩固（Consolidation）
        - 合并相似实体
        - 标记过时事实
        - 抽象通用模式
        - 清理低价值记忆
        """
        before_count = len(self._memories)
        removed = 0
        merged = 0

        # 1. 合并相似实体
        entity_names = list(self._entities.keys())
        for i, name1 in enumerate(entity_names):
            for name2 in entity_names[i + 1:]:
                if name1 in name2 or name2 in name1:
                    # 合并到更短的名称
                    keep = name1 if len(name1) < len(name2) else name2
                    remove = name2 if keep == name1 else name1
                    if remove in self._entities and keep in self._entities:
                        self._entities[keep]["mention_count"] += self._entities[remove].get("mention_count", 0)
                        self._entities[keep]["relations"].extend(self._entities[remove].get("relations", []))
                        del self._entities[remove]
                        merged += 1

        # 2. 标记过时事实（相同主题的新事实标记旧事实）
        facts = [m for m in self._memories.values() if m.memory_type == "fact"]
        for i, f1 in enumerate(facts):
            for f2 in facts[i + 1:]:
                if f1.content[:20] == f2.content[:20] and f1.created_at < f2.created_at:
                    f1.is_obsolete = True
                    f2.related_ids.append(f1.id)

        # 3. 清理低价值记忆（访问次数为0且重要性<0.3且超过7天）
        now = time.time()
        to_remove = []
        for mid, item in self._memories.items():
            age_days = (now - item.created_at) / 86400
            if item.access_count == 0 and item.importance < 0.3 and age_days > 7:
                to_remove.append(mid)
        for mid in to_remove:
            del self._memories[mid]
            removed += 1

        self._save()

        return {
            "before_count": before_count,
            "after_count": len(self._memories),
            "entities_merged": merged,
            "low_value_removed": removed,
            "consolidated_at": datetime.now().isoformat(),
        }

    def get_stats(self) -> dict:
        """获取记忆统计"""
        type_counts: dict[str, int] = {}
        for item in self._memories.values():
            type_counts[item.memory_type] = type_counts.get(item.memory_type, 0) + 1
        return {
            "project_id": self.project_id,
            "total_memories": len(self._memories),
            "by_type": type_counts,
            "entities_count": len(self._entities),
            "relations_count": len(self._relations),
            "core_memory_count": len(self._core_memory),
            "obsolete_count": sum(1 for m in self._memories.values() if m.is_obsolete),
            "storage_path": self._storage_path,
        }

    def _extract_entities_and_relations(self, content: str, memory_id: str) -> None:
        """从内容中抽取实体与关系（MVP简单规则版）"""
        # 实体抽取：匹配常见业务实体模式
        entity_patterns = [
            ("system", ["系统", "平台", "模块", "引擎", "服务"]),
            ("role", ["管理员", "业务人员", "客户", "审核员", "开发者"]),
            ("document", ["文档", "报告", "工单", "合同", "方案", "需求"]),
            ("concept", ["流程", "规则", "指标", "标准", "模型", "算法"]),
        ]
        for etype, keywords in entity_patterns:
            for kw in keywords:
                if kw in content:
                    # 提取包含关键词的短语作为实体
                    for sentence in content.replace("。", "。").split("。"):
                        if kw in sentence and len(sentence) < 50:
                            entity_name = sentence.strip()[:30]
                            if entity_name not in self._entities:
                                self._entities[entity_name] = {
                                    "type": etype,
                                    "mention_count": 0,
                                    "relations": [],
                                    "first_seen": memory_id,
                                }
                            self._entities[entity_name]["mention_count"] += 1

        # 关系抽取：匹配"A的B"模式
        import re
        relation_matches = re.findall(r"([^，。；的]{2,15})的([^，。；]{2,15})", content)
        for subj, obj in relation_matches[:5]:
            self._relations.append({
                "subject": subj.strip(),
                "predicate": "的",
                "object": obj.strip(),
                "memory_id": memory_id,
                "timestamp": time.time(),
            })

    def _save(self) -> None:
        """持久化到JSON文件"""
        try:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            data = {
                "project_id": self.project_id,
                "memories": [m.to_dict() for m in self._memories.values()],
                "entities": self._entities,
                "relations": self._relations,
                "core_memory": self._core_memory,
                "saved_at": time.time(),
            }
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 持久化失败不阻断主流程

    def _load(self) -> None:
        """从JSON文件加载"""
        try:
            if os.path.exists(self._storage_path):
                with open(self._storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for m_data in data.get("memories", []):
                    item = MemoryItem(
                        id=m_data["id"],
                        content=m_data["content"],
                        memory_type=m_data.get("memory_type", "fact"),
                        project_id=m_data.get("project_id", self.project_id),
                        metadata=m_data.get("metadata", {}),
                        created_at=m_data.get("created_at", time.time()),
                        updated_at=m_data.get("updated_at", time.time()),
                        importance=m_data.get("importance", 0.5),
                        access_count=m_data.get("access_count", 0),
                        last_accessed=m_data.get("last_accessed", time.time()),
                        is_obsolete=m_data.get("is_obsolete", False),
                        related_ids=m_data.get("related_ids", []),
                    )
                    self._memories[item.id] = item
                self._entities = data.get("entities", {})
                self._relations = data.get("relations", [])
                self._core_memory = data.get("core_memory", [])
        except Exception:
            pass  # 加载失败从空开始


def get_memory_manager(project_id: str) -> MemoryManager:
    """获取记忆管理器单例"""
    return MemoryManager.get_instance(project_id)
