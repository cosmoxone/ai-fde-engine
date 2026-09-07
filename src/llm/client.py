"""
LLM客户端 - 支持OpenAI兼容API（DeepSeek、Qwen、本地vLLM等）
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from src.config import get_settings


@dataclass
class LLMMessage:
    role: str
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = ""
    raw: Any = None

    def parse_json(self) -> dict:
        try:
            content = self.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            return {}


@dataclass
class LLMCost:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMClient:
    MODEL_PRICING = {
        "deepseek-v4-pro": {"input": 0.002, "output": 0.008},
        "deepseek-v4-flash": {"input": 0.0005, "output": 0.002},
        "qwen3.6-27b": {"input": 0.001, "output": 0.004},
        "qwen3.5-397b": {"input": 0.003, "output": 0.012},
        "default": {"input": 0.002, "output": 0.008},
    }

    def __init__(self, project_id: str = "default"):
        self.settings = get_settings()
        self.project_id = project_id
        self._client: Optional[httpx.AsyncClient] = None
        self._total_cost = LLMCost()
        self._call_count = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=30.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_model_config(self, model: str) -> tuple[str, str, str]:
        if model.startswith("deepseek"):
            return self.settings.deepseek_base_url, self.settings.deepseek_api_key, model
        elif model.startswith("qwen"):
            return self.settings.qwen_base_url, self.settings.qwen_api_key, model
        else:
            return self.settings.deepseek_base_url, self.settings.deepseek_api_key, model

    async def chat(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        if model is None:
            model = self.settings.get_model_for_task("code")[0]

        base_url, api_key, actual_model = self._get_model_config(model)

        if not api_key:
            return self._mock_chat(messages, model)

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        last_error = None

        for attempt in range(max_retries):
            try:
                start_time = time.time()
                client = await self._get_client()
                response = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
                latency_ms = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()
                    choice = data["choices"][0]
                    msg = choice.get("message", {})
                    usage = data.get("usage", {})
                    result = LLMResponse(
                        content=msg.get("content", ""),
                        model=actual_model,
                        usage=usage,
                        latency_ms=latency_ms,
                        finish_reason=choice.get("finish_reason", ""),
                        raw=data,
                    )
                    self._track_cost(actual_model, usage)
                    self._call_count += 1
                    return result
                elif response.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(2 ** attempt)
                    last_error = f"HTTP {response.status_code}, attempt {attempt+1}"
                else:
                    return LLMResponse(
                        content=f"[LLM_ERROR] HTTP {response.status_code}: {response.text[:500]}",
                        model=actual_model,
                        latency_ms=latency_ms,
                        finish_reason="error",
                    )
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                await asyncio.sleep(2 ** attempt)
                last_error = f"{type(e).__name__}: {str(e)}, attempt {attempt+1}"
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)}"
                break

        return LLMResponse(
            content=f"[LLM_ERROR] All retries failed: {last_error}",
            model=model,
            finish_reason="error",
        )

    async def chat_json(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        schema: Optional[dict] = None,
    ) -> tuple[LLMResponse, dict]:
        response_format = {"type": "json_object"}
        if schema:
            schema_text = f"\n\n请严格按以下JSON结构输出：\n```json\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n```"
            if messages and messages[-1].role == "user":
                messages[-1].content += schema_text
            else:
                messages.append(LLMMessage("user", schema_text))

        response = await self.chat(messages=messages, model=model, temperature=temperature,
                                    max_tokens=max_tokens, response_format=response_format)
        return response, response.parse_json()

    def _mock_chat(self, messages: list[LLMMessage], model: str) -> LLMResponse:
        user_content = ""
        for m in messages:
            if m.role == "user":
                user_content = m.content
                break
        return LLMResponse(
            content=f"[Mock] 模型{model}模拟响应。输入: {user_content[:80]}... 配置DEEPSEEK_API_KEY或QWEN_API_KEY启用真实调用。",
            model=model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            latency_ms=1.0,
            finish_reason="mock",
        )

    def _track_cost(self, model: str, usage: dict):
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        pricing = self.MODEL_PRICING.get(model, self.MODEL_PRICING["default"])
        cost = input_tokens / 1_000_000 * pricing["input"] + output_tokens / 1_000_000 * pricing["output"]
        self._total_cost.input_tokens += input_tokens
        self._total_cost.output_tokens += output_tokens
        self._total_cost.total_tokens += input_tokens + output_tokens
        self._total_cost.estimated_cost_usd += cost

    def get_total_cost(self) -> LLMCost:
        return self._total_cost

    def get_call_count(self) -> int:
        return self._call_count


_clients: dict[str, LLMClient] = {}


def get_llm_client(project_id: str = "default") -> LLMClient:
    if project_id not in _clients:
        _clients[project_id] = LLMClient(project_id)
    return _clients[project_id]
