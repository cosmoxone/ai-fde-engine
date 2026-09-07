"""
配置管理模块 - 基于Pydantic Settings，支持环境变量覆盖
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """系统全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 系统配置 =====
    app_name: str = "AI-FDE Engine"
    app_env: Literal["development", "production", "testing"] = "production"
    app_debug: bool = False
    app_port: int = 8000
    secret_key: str = Field(default="change-me-in-production", min_length=16)
    jwt_secret: str = Field(default="change-me-in-production", min_length=16)
    jwt_expire_hours: int = 24
    cors_origins: str = "*"
    log_level: str = "INFO"
    log_format: str = "json"

    # ===== 管理员 =====
    admin_email: str = "admin@example.com"
    admin_password: str = "ChangeMe@2026"
    admin_name: str = "Administrator"

    # ===== LLM配置 =====
    llm_provider: Literal["deepseek", "qwen", "openai", "ollama", "custom"] = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_code_model: str = "deepseek-v4-pro"
    deepseek_fast_model: str = "deepseek-v4-flash"
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_research_model: str = "qwen3.6-27b"
    qwen_long_context_model: str = "qwen3.5-397b"
    local_model_base_url: str = "http://vllm:8000/v1"
    local_model_api_key: str = "not-needed"
    local_model_name: str = "qwen3.6-27b"

    # 模型路由
    model_routing_enabled: bool = True
    model_task_code: str = "deepseek-v4-pro"
    model_task_research: str = "qwen3.6-27b"
    model_task_design: str = "deepseek-v4-pro"
    model_task_evaluation: str = "deepseek-v4-flash"
    model_task_project: str = "qwen3.6-27b"

    # ===== 数据库 =====
    postgres_host: str = "postgresql"
    postgres_port: int = 5432
    postgres_db: str = "aifde"
    postgres_user: str = "aifde"
    postgres_password: str = "aifde_password"
    postgres_pool_size: int = 20

    # ===== 向量库 =====
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_collection_prefix: str = "aifde_"

    # ===== 对象存储 =====
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "aifde_minio"
    minio_secret_key: str = "aifde_minio_secret"
    minio_bucket: str = "aifde-documents"
    minio_secure: bool = False

    # ===== Redis =====
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_cache_ttl: int = 3600

    # ===== 记忆系统 =====
    memory_provider: Literal["zep", "mem0", "letta", "hybrid", "mock"] = "mem0"
    memory_graph_enabled: bool = True
    memory_temporal_enabled: bool = True
    memory_consolidation_cron: str = "0 3 * * *"
    memory_cross_project_search: bool = True
    letta_api_url: str = ""
    letta_api_key: str = ""

    # ===== 文档解析 =====
    doc_parser_provider: Literal["marker", "docling", "hybrid", "mock"] = "docling"
    doc_parser_marker_gpu: bool = False
    doc_parser_batch_size: int = 5
    doc_parser_timeout: int = 300
    doc_parser_language: str = "chinese"

    # ===== 知识库 =====
    kb_provider: Literal["lightrag", "graphrag", "qdrant", "basic", "mock"] = "qdrant"
    kb_embedding_model: str = "bge-m3"
    kb_embedding_dim: int = 1024
    kb_chunk_size: int = 1024
    kb_chunk_overlap: int = 128
    kb_graph_extraction_enabled: bool = True
    kb_incremental_update: bool = True

    # ===== Benchmark =====
    benchmark_default_case_count: int = 50
    benchmark_category_ratio: str = "high_frequency:0.6,edge:0.3,adversarial:0.1"
    benchmark_auto_generation: bool = True
    benchmark_adversarial_enabled: bool = True

    # ===== 评测 =====
    evaluation_provider: Literal["deepeval", "mock"] = "deepeval"
    evaluation_gate_enabled: bool = True
    evaluation_gate_accuracy: float = 0.8
    evaluation_gate_hallucination: float = 0.1
    evaluation_gate_recall: float = 0.85
    evaluation_auto_run_on_version: bool = True

    # ===== 代码生成 =====
    code_gen_provider: Literal["openhands", "aider", "opencode", "mock"] = "aider"
    code_gen_sandbox_enabled: bool = True
    code_gen_timeout: int = 3600
    code_gen_max_retries: int = 3
    code_gen_auto_test: bool = True
    code_gen_auto_lint: bool = True
    openhands_sandbox_type: str = "docker"
    openhands_workspace_base: str = "/tmp/openhands-workspaces"

    # ===== 迭代流水线 =====
    iteration_enabled: bool = True
    iteration_cron: str = "0 20 * * *"
    iteration_max_badcases: int = 20
    iteration_auto_deploy: bool = True
    iteration_auto_rollback: bool = True
    iteration_notification_webhook: str = ""

    # ===== 可观测性 =====
    observability_provider: Literal["langfuse", "none"] = "none"
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    trace_enabled: bool = True
    trace_sample_rate: float = 1.0

    # ===== 自助交付（F7）=====
    self_service_enabled: bool = True
    self_service_guidance_mode: bool = True  # 引导模式：步骤化引导非技术用户
    self_service_auto_deviation_detection: bool = True  # 自动纠偏检测
    self_service_fde_review_required: bool = True  # 关键节点需要FDE审核
    self_service_prototype_trial_days: int = 14  # 原型试用期（天）
    self_service_max_modules_mvp: int = 5  # MVP最大功能模块数（超过触发纠偏）
    self_service_min_budget_threshold: int = 50000  # 最低预算阈值（元）
    self_service_feedback_sla_hours: int = 24  # 反馈响应SLA（小时）
    self_service_value_dashboard_enabled: bool = True  # 价值仪表盘
    self_service_training_push_enabled: bool = True  # 培训内容推送

    # ===== 安全 =====
    security_sensitive_filter: bool = True
    security_prompt_injection_protection: bool = True
    security_output_audit: bool = True
    security_data_encryption: bool = True
    security_rate_limit_enabled: bool = True
    security_rate_limit_per_minute: int = 60

    # ===== 派生属性 =====
    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_dsn(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    def get_model_for_task(self, task: str) -> tuple[str, str, str]:
        """根据任务类型获取模型配置 (model_name, base_url, api_key)"""
        task_map = {
            "code": self.model_task_code,
            "research": self.model_task_research,
            "design": self.model_task_design,
            "evaluation": self.model_task_evaluation,
            "project": self.model_task_project,
        }
        model_name = task_map.get(task, self.deepseek_code_model)
        if model_name.startswith("deepseek"):
            return model_name, self.deepseek_base_url, self.deepseek_api_key
        elif model_name.startswith("qwen"):
            return model_name, self.qwen_base_url, self.qwen_api_key
        else:
            return model_name, self.local_model_base_url, self.local_model_api_key

    @field_validator("app_env")
    @classmethod
    def set_debug_from_env(cls, v: str) -> str:
        return v


@lru_cache
def get_settings() -> Settings:
    """获取单例配置"""
    return Settings()
