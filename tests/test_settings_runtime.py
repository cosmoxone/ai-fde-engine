"""
Web 配置引导测试（v0.1.1 A3）：运行时设置 + 热生效
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.settings_runtime import (
    _mask,
    get_llm_status,
    load_runtime_settings,
    save_llm_settings,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """独立 data 目录的测试客户端"""
    monkeypatch.setenv("AIFDE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STORAGE_PROVIDER", "memory")
    from src.main import app

    with TestClient(app) as c:
        yield c


class TestSettingsAPI:
    def test_get_default_mock_status(self, client):
        resp = client.get("/api/v1/settings/llm")
        assert resp.status_code == 200
        llm = resp.json()["llm"]
        assert llm["mode"] in ("mock", "real")
        assert "api_key" not in json.dumps(llm) or not llm.get("api_key")

    def test_post_saves_and_hot_applies(self, client):
        resp = client.post(
            "/api/v1/settings/llm",
            json={"provider": "deepseek", "api_key": "sk-test-1234567890abcdef"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["llm"]["mode"] == "real"
        # 热生效：settings 单例已更新
        assert get_settings().deepseek_api_key == "sk-test-1234567890abcdef"
        # 持久化到 data/settings.json
        settings_file = os.path.join(os.environ["AIFDE_DATA_DIR"], "settings.json")
        saved = json.loads(open(settings_file, encoding="utf-8").read())
        assert saved["deepseek_api_key"] == "sk-test-1234567890abcdef"
        assert saved["llm_provider"] == "deepseek"

    def test_key_masked_in_status(self, client):
        client.post("/api/v1/settings/llm", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcdef"})
        resp = client.get("/api/v1/settings/llm")
        masked = resp.json()["llm"]["api_key_masked"]
        assert "1234567890" not in masked
        assert masked == "sk-t***cdef"

    def test_invalid_provider_rejected(self, client):
        resp = client.post("/api/v1/settings/llm", json={"provider": "gpt4", "api_key": "x"})
        assert resp.status_code == 400

    def test_health_reflects_real_mode(self, client):
        client.post("/api/v1/settings/llm", json={"provider": "deepseek", "api_key": "sk-test-1234567890abcdef"})
        health = client.get("/api/v1/health").json()
        assert health["services"]["llm_api"] == "configured"


class TestRuntimeSettingsUnit:
    def test_load_runtime_settings_on_restart(self, tmp_path, monkeypatch):
        """重启恢复：写入 → 新进程 load → 单例恢复"""
        data_dir = str(tmp_path / "data")
        monkeypatch.setenv("AIFDE_DATA_DIR", data_dir)
        save_llm_settings("qwen", "sk-qwen-9876543210", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

        # 模拟重启：清空单例中的值，再 load
        settings = get_settings()
        settings.qwen_api_key = ""
        assert get_llm_status()["mode"] == "mock" or get_llm_status()["provider"] != "qwen"
        loaded = load_runtime_settings()
        assert loaded is True
        assert settings.qwen_api_key == "sk-qwen-9876543210"
        assert get_llm_status()["mode"] == "real"

    def test_load_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIFDE_DATA_DIR", str(tmp_path / "nope"))
        assert load_runtime_settings() is False

    def test_corrupt_file_ignored(self, tmp_path, monkeypatch):
        data_dir = str(tmp_path / "data")
        monkeypatch.setenv("AIFDE_DATA_DIR", data_dir)
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "settings.json"), "w") as f:
            f.write("{broken json")
        assert load_runtime_settings() is False

    def test_mask(self):
        assert _mask("sk-1234567890abcdef") == "sk-1***cdef"
        assert _mask("short") == "***"
        assert _mask("") == ""
