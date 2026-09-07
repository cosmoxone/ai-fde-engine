"""
记忆模块测试
"""

import os

import pytest

from src.memory import MemoryItem, MemoryManager


@pytest.fixture
def memory_manager(tmp_path):
    """测试用记忆管理器"""
    os.environ["MEMORY_STORAGE_DIR"] = str(tmp_path)
    manager = MemoryManager.get_instance("test_project")
    # 清空已有记忆
    manager._memories.clear()
    manager._entities.clear()
    manager._relations.clear()
    manager._core_memory.clear()
    yield manager
    # 清理单例
    if "test_project" in MemoryManager._instances:
        del MemoryManager._instances["test_project"]


class TestMemoryManager:
    """记忆管理器测试"""

    @pytest.mark.asyncio
    async def test_remember_fact(self, memory_manager):
        """测试记录事实"""
        item = await memory_manager.remember(
            content="客户业务流程包含受理、审核、处理三个环节",
            memory_type="fact",
            importance=0.8,
        )
        assert item.id is not None
        assert item.content == "客户业务流程包含受理、审核、处理三个环节"
        assert item.memory_type == "fact"
        assert item.importance == 0.8
        assert item.id in memory_manager._memories

    @pytest.mark.asyncio
    async def test_remember_event(self, memory_manager):
        """测试记录事件"""
        item = await memory_manager.remember(
            content="项目启动会议完成，确定MVP范围",
            memory_type="event",
        )
        assert item.memory_type == "event"

    @pytest.mark.asyncio
    async def test_recall_by_keyword(self, memory_manager):
        """测试关键词检索"""
        await memory_manager.remember("业务审核流程需要3个工作日", memory_type="fact")
        await memory_manager.remember("系统部署在Docker容器中", memory_type="fact")
        await memory_manager.remember("知识库使用LightRAG构建", memory_type="fact")

        results = await memory_manager.recall("审核流程", limit=5)
        assert len(results) > 0
        assert any("审核" in r.content for r in results)

    @pytest.mark.asyncio
    async def test_recall_limit(self, memory_manager):
        """测试检索数量限制"""
        for i in range(20):
            await memory_manager.remember(f"测试记忆条目{i}：业务相关内容", memory_type="fact")
        results = await memory_manager.recall("业务", limit=5)
        assert len(results) <= 5

    @pytest.mark.asyncio
    async def test_recall_by_type(self, memory_manager):
        """测试按类型检索"""
        await memory_manager.remember("这是一个事实", memory_type="fact")
        await memory_manager.remember("这是一个事件", memory_type="event")
        await memory_manager.remember("这是一个经验", memory_type="experience")

        results = await memory_manager.recall("记忆", memory_type="event", limit=10)
        assert all(r.memory_type == "event" for r in results)

    @pytest.mark.asyncio
    async def test_get_project_context_empty(self, memory_manager):
        """测试空项目上下文"""
        context = await memory_manager.get_project_context()
        assert "暂无项目记忆" in context

    @pytest.mark.asyncio
    async def test_get_project_context_with_memory(self, memory_manager):
        """测试有记忆的项目上下文"""
        await memory_manager.remember("客户名称：测试公司", memory_type="fact", importance=0.9)
        await memory_manager.remember("项目启动完成", memory_type="event")
        context = await memory_manager.get_project_context()
        assert "测试公司" in context or "项目启动" in context

    @pytest.mark.asyncio
    async def test_high_importance_to_core_memory(self, memory_manager):
        """测试高重要性记忆加入Core Memory"""
        await memory_manager.remember("这是非常重要的项目约束", memory_type="fact", importance=0.9)
        assert len(memory_manager._core_memory) > 0
        assert any("重要" in m for m in memory_manager._core_memory)

    @pytest.mark.asyncio
    async def test_entity_extraction(self, memory_manager):
        """测试实体抽取"""
        await memory_manager.remember("业务系统中的客户管理模块负责客户信息维护", memory_type="fact")
        assert len(memory_manager._entities) > 0

    @pytest.mark.asyncio
    async def test_consolidate(self, memory_manager):
        """测试记忆巩固"""
        for i in range(10):
            await memory_manager.remember(f"低价值记忆{i}", memory_type="fact", importance=0.1)
        before = len(memory_manager._memories)
        result = await memory_manager.consolidate()
        assert result["before_count"] == before
        assert "after_count" in result
        assert "entities_merged" in result
        assert "low_value_removed" in result

    @pytest.mark.asyncio
    async def test_get_stats(self, memory_manager):
        """测试记忆统计"""
        await memory_manager.remember("测试统计1", memory_type="fact")
        await memory_manager.remember("测试统计2", memory_type="event")
        stats = memory_manager.get_stats()
        assert stats["project_id"] == "test_project"
        assert stats["total_memories"] == 2
        assert "by_type" in stats
        assert stats["by_type"].get("fact") == 1
        assert stats["by_type"].get("event") == 1

    @pytest.mark.asyncio
    async def test_memory_persistence(self, memory_manager, tmp_path):
        """测试记忆持久化"""
        await memory_manager.remember("持久化测试记忆", memory_type="fact")
        # 创建新实例，验证从文件加载
        if "test_project" in MemoryManager._instances:
            del MemoryManager._instances["test_project"]
        new_manager = MemoryManager.get_instance("test_project")
        assert len(new_manager._memories) > 0
        assert any("持久化" in m.content for m in new_manager._memories.values())
        # 清理
        if "test_project" in MemoryManager._instances:
            del MemoryManager._instances["test_project"]

    @pytest.mark.asyncio
    async def test_obsolete_memory_not_recalled(self, memory_manager):
        """测试过时记忆不被检索"""
        item = await memory_manager.remember("过时的业务规则", memory_type="fact")
        item.is_obsolete = True
        results = await memory_manager.recall("业务规则", limit=10)
        assert not any("过时" in r.content for r in results)


class TestMemoryItem:
    """MemoryItem测试"""

    def test_to_dict(self):
        """测试序列化"""
        item = MemoryItem(id="1", content="test", memory_type="fact")
        d = item.to_dict()
        assert d["id"] == "1"
        assert d["content"] == "test"
        assert d["memory_type"] == "fact"
