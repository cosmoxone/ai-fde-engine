"""知识库契约测试 - 共享 fixture。

环境变量:
  KB_BASE_URL      被测服务地址(默认 http://127.0.0.1:9000)
  KB_PROFILE       断言适配:spec14(默认)| kbos
  KB_TOKEN         可选;设置后:① 客户端带 Bearer 头 ② 启用鉴权负例用例
  KB_INDEX_TIMEOUT 最终一致等待上限秒数(默认 300)

契约源:docs/14-知识库接口规格.md v1.2;kb-os 映射:09-ai-fde对接方案 §4。
"""

from __future__ import annotations

import os
import time

import pytest

from .adapters_kbos import KbOsClient
from .adapters_spec14 import Spec14Client
from .core import KBClient, Stats, marker_token

KB_BASE_URL = os.environ.get("KB_BASE_URL", "http://127.0.0.1:9000").rstrip("/")
KB_TOKEN = os.environ.get("KB_TOKEN", "")
KB_PROFILE = os.environ.get("KB_PROFILE", "spec14").strip().lower()
KB_INDEX_TIMEOUT = float(os.environ.get("KB_INDEX_TIMEOUT", "300"))
POLL_INTERVAL = 2.0

_ADAPTERS = {"spec14": Spec14Client, "kbos": KbOsClient}


def wait_ready(client: KBClient, expect_documents: int = 0, timeout: float = KB_INDEX_TIMEOUT) -> Stats:
    """最终一致等待:轮询 stats 至 parsing == 0 且 documents >= expect_documents。

    就绪判据模式无关(规格 §3.6);同步实现(恒 0)首次轮询即通过。
    """
    deadline = time.monotonic() + timeout
    last: Stats | None = None
    while time.monotonic() < deadline:
        last = client.stats()
        if last.parsing == 0 and last.documents >= expect_documents:
            return last
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"索引未在 {timeout}s 内收敛: stats={last} (期望 parsing==0 且 documents>={expect_documents})")


@pytest.fixture(scope="session")
def kb() -> KBClient:
    """按 KB_PROFILE 构造断言适配器(会话级复用连接)"""
    if KB_PROFILE not in _ADAPTERS:
        raise ValueError(f"未知 KB_PROFILE={KB_PROFILE},可选: {sorted(_ADAPTERS)}")
    client = _ADAPTERS[KB_PROFILE](KB_BASE_URL, token=KB_TOKEN)
    yield client
    client.close()


@pytest.fixture(scope="session")
def wait():
    """暴露 wait_ready 给用例(场景内复用最终一致等待)"""
    return wait_ready


@pytest.fixture(scope="session")
def marker() -> str:
    """本次运行的全局唯一检索标记(保证断言确定性,不依赖实现方语料)"""
    return marker_token()
