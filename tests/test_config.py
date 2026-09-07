"""
配置模块测试
"""

import pytest

from src.config import Settings, get_settings


class TestSettings:
    """配置测试"""

    def test_default_settings(self):
        """测试默认配置加载"""
        settings = Settings()
        assert settings.app_name == "AI-FDE Engine"
        assert settings.app_port == 8000
        assert settings.postgres_port == 5432
        assert settings.qdrant_port == 6333
        assert settings.redis_port == 6379

    def test_postgres_dsn(self):
        """测试PostgreSQL DSN生成"""
        settings = Settings(
            postgres_host="localhost",
            postgres_port=5432,
            postgres_db="testdb",
            postgres_user="user",
            postgres_password="pass",
        )
        dsn = settings.postgres_dsn
        assert "localhost" in dsn
        assert "testdb" in dsn
        assert "user" in dsn
        assert "postgresql" in dsn

    def test_redis_dsn(self):
        """测试Redis DSN生成"""
        settings = Settings(redis_host="localhost", redis_port=6379, redis_db=1)
        dsn = settings.redis_dsn
        assert "localhost" in dsn
        assert "6379" in dsn
        assert "/1" in dsn

    def test_qdrant_url(self):
        """测试Qdrant URL生成"""
        settings = Settings(qdrant_host="localhost", qdrant_port=6333)
        assert settings.qdrant_url == "http://localhost:6333"

    def test_get_model_for_task_deepseek(self):
        """测试DeepSeek模型路由"""
        settings = Settings(
            deepseek_api_key="test-key",
            deepseek_base_url="https://api.test.com/v1",
            model_task_code="deepseek-v4-pro",
        )
        model, base_url, api_key = settings.get_model_for_task("code")
        assert model == "deepseek-v4-pro"
        assert base_url == "https://api.test.com/v1"
        assert api_key == "test-key"

    def test_get_model_for_task_qwen(self):
        """测试Qwen模型路由"""
        settings = Settings(
            qwen_api_key="qwen-key",
            qwen_base_url="https://qwen.test.com/v1",
            model_task_research="qwen3.6-27b",
        )
        model, base_url, api_key = settings.get_model_for_task("research")
        assert model == "qwen3.6-27b"
        assert "qwen" in base_url

    def test_invalid_app_env(self):
        """测试无效环境值"""
        with pytest.raises(Exception):
            Settings(app_env="invalid_env")

    def test_secret_key_min_length(self):
        """测试密钥最小长度"""
        with pytest.raises(Exception):
            Settings(secret_key="short")

    def test_settings_singleton(self):
        """测试配置单例"""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
