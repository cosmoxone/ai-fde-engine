"""
运行时设置（v0.1.1 A3：Web 配置引导）

目标：单机用户无需手动编辑 .env——在 Dashboard 填 LLM API Key，
持久化到 data/settings.json 并热生效（新请求即用新 Key）。

安全定位：单机本机使用；Key 以明文存于本地 data/settings.json
（与 .env 同级安全边界，仓库 .gitignore 已忽略 data/）。
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .config import Settings, get_settings

SETTINGS_FILENAME = "settings.json"

# 允许通过运行时设置覆盖的配置键（白名单，防止任意改写）
_ALLOWED_KEYS = {
    "llm_provider",
    "deepseek_api_key",
    "deepseek_base_url",
    "qwen_api_key",
    "qwen_base_url",
}

_PROVIDER_KEY_MAP = {
    "deepseek": ("deepseek_api_key", "deepseek_base_url"),
    "qwen": ("qwen_api_key", "qwen_base_url"),
}


def _settings_path(settings: Settings) -> str:
    return os.path.join(os.environ.get("AIFDE_DATA_DIR", settings.data_dir), SETTINGS_FILENAME)


def load_runtime_settings() -> bool:
    """启动时加载 data/settings.json 覆盖 settings 单例；文件不存在返回 False"""
    settings = get_settings()
    path = _settings_path(settings)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            overrides = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    for key, value in overrides.items():
        if key in _ALLOWED_KEYS and isinstance(value, str) and value:
            setattr(settings, key, value)
    return True


def save_llm_settings(provider: str, api_key: str, base_url: Optional[str] = None) -> dict:
    """
    保存 LLM 配置并热生效。

    provider: deepseek / qwen / openai / ollama / custom
    返回脱敏后的状态摘要。
    """
    if provider not in _PROVIDER_KEY_MAP and provider not in ("openai", "ollama", "custom"):
        raise ValueError(f"不支持的 provider: {provider}")

    settings = get_settings()
    overrides: dict[str, str] = {"llm_provider": provider}

    # 将 key 写入对应 provider 的配置位
    key_field, url_field = _PROVIDER_KEY_MAP.get(provider, ("deepseek_api_key", "deepseek_base_url"))
    setattr(settings, key_field, api_key)
    overrides[key_field] = api_key
    if base_url:
        setattr(settings, url_field, base_url)
        overrides[url_field] = base_url

    # 持久化：读取现有覆盖项合并写回
    path = _settings_path(settings)
    existing: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing.update(overrides)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    return get_llm_status()


def get_llm_status() -> dict:
    """当前 LLM 配置状态（Key 脱敏，不返回明文）"""
    settings = get_settings()
    provider = settings.llm_provider
    key = settings.deepseek_api_key if provider in ("deepseek", "openai", "custom") else settings.qwen_api_key
    if provider == "qwen":
        base_url = settings.qwen_base_url
    else:
        base_url = settings.deepseek_base_url
    return {
        "provider": provider,
        "configured": bool(key),
        "api_key_masked": _mask(key) if key else "",
        "base_url": base_url,
        "mode": "real" if key else "mock",
    }


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"
