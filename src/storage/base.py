"""
存储层抽象 - 业务数据持久化的统一接口（v0.1.1 A1）

设计目标：
- CE 默认 SQLite 单文件（data/aifde.db），重启不丢数据
- 内存实现保留给测试/演示（STORAGE_PROVIDER=memory）
- TE 商业版可通过本扩展点替换为 PostgreSQL 后端（v0.1.1 A5 预留）

数据形态：所有实体均为 dict（JSON 兼容），存储层不做 schema 校验，
序列化策略由各实现自定（memory 原样 / sqlite JSON 列）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class StorageProvider(ABC):
    """
    存储提供方抽象接口

    实现要求（契约）：
    - 所有方法线程安全（FastAPI BackgroundTasks 可能跨线程）
    - dict 内容为 JSON 可序列化（嵌套 dict/list/str/num/bool/None）
    - get/list 找不到时返回 None / 空列表（不抛异常）
    - update_* 找不到目标时返回 None
    """

    # ===== 项目 =====
    @abstractmethod
    def create_project(self, project: dict) -> None:
        """创建项目（project["id"] 为主键）"""

    @abstractmethod
    def get_project(self, project_id: str) -> Optional[dict]:
        """获取项目，不存在返回 None"""

    @abstractmethod
    def list_projects(self) -> list[dict]:
        """列出全部项目"""

    @abstractmethod
    def update_project(self, project_id: str, fields: dict) -> Optional[dict]:
        """部分更新项目字段，返回更新后的完整 dict；不存在返回 None"""

    # ===== 文档 =====
    @abstractmethod
    def add_document(self, project_id: str, doc: dict) -> None:
        """追加项目文档记录"""

    @abstractmethod
    def list_documents(self, project_id: str) -> list[dict]:
        """列出项目全部文档（按加入顺序）"""

    # ===== 异步任务 =====
    @abstractmethod
    def create_task(self, task: dict) -> None:
        """创建任务记录（以 task["id"] 或 task["task_id"] 为主键）"""

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务，不存在返回 None"""

    @abstractmethod
    def update_task(self, task_id: str, fields: dict) -> Optional[dict]:
        """部分更新任务字段（status/result/error 等）"""

    @abstractmethod
    def list_tasks(self, project_id: Optional[str] = None) -> list[dict]:
        """列出任务；指定 project_id 时按其过滤"""

    # ===== Benchmark =====
    @abstractmethod
    def save_benchmark(self, benchmark: dict) -> None:
        """保存/覆盖 Benchmark（benchmark["benchmark_id"] 为主键）"""

    @abstractmethod
    def get_benchmark(self, benchmark_id: str) -> Optional[dict]:
        """获取 Benchmark"""

    @abstractmethod
    def list_benchmarks(self, project_id: Optional[str] = None) -> list[dict]:
        """列出 Benchmark；指定 project_id 时按其过滤"""

    # ===== 审核队列 =====
    @abstractmethod
    def add_review(self, review: dict) -> dict:
        """加入审核队列，返回存储后的 review（含 review_id）"""

    @abstractmethod
    def get_review(self, review_id: str) -> Optional[dict]:
        """获取审核项"""

    @abstractmethod
    def list_reviews(self, status: Optional[str] = None) -> list[dict]:
        """列出审核项；指定 status 时按其过滤（如 pending）"""

    @abstractmethod
    def update_review(self, review_id: str, fields: dict) -> Optional[dict]:
        """更新审核项（status/comment/reviewer）"""

    # ===== 客户反馈 =====
    @abstractmethod
    def add_feedback(self, project_id: str, feedback: dict) -> None:
        """追加项目反馈"""

    @abstractmethod
    def list_feedback(self, project_id: str) -> list[dict]:
        """列出项目全部反馈（按时间顺序）"""

    # ===== Badcase（v0.1.2 B5）=====
    @abstractmethod
    def add_badcase(self, badcase: dict) -> None:
        """保存 Badcase（badcase["id"] 为主键，status: open/processed）"""

    @abstractmethod
    def get_badcase(self, badcase_id: str) -> Optional[dict]:
        """获取 Badcase"""

    @abstractmethod
    def list_badcases(self, project_id: Optional[str] = None, status: Optional[str] = None) -> list[dict]:
        """列出 Badcase，可按项目/状态过滤"""

    @abstractmethod
    def update_badcase(self, badcase_id: str, fields: dict) -> Optional[dict]:
        """更新 Badcase（status/error_type 等）"""

    # ===== 统计 =====
    @abstractmethod
    def count_running_tasks(self) -> int:
        """当前 running 状态任务数（健康检查用）"""
