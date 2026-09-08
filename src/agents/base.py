"""
Agent基类 - 基于Pydantic AI V2风格的类型安全Agent
统一注入：记忆、工具、评测、护栏、可观测性等横切能力
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..config import get_settings
from ..llm import LLMClient, LLMMessage, get_llm_client
from ..memory import MemoryManager, get_memory_manager


@dataclass
class AgentResult:
    """Agent执行结果"""

    success: bool
    content: str = ""
    structured_output: Optional[dict[str, Any]] = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "structured_output": self.structured_output,
            "tool_calls": self.tool_calls,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


@dataclass
class AgentCapability:
    """Agent能力插件 - 对应Pydantic AI V2的Capability机制"""

    name: str
    description: str = ""
    # 钩子函数
    before_run: Optional[Callable[["BaseAgent", dict[str, Any]], None]] = None
    after_run: Optional[Callable[["BaseAgent", AgentResult], AgentResult]] = None
    on_tool_call: Optional[Callable[["BaseAgent", str, dict], tuple[str, dict]]] = None
    on_error: Optional[Callable[["BaseAgent", Exception], Optional[AgentResult]]] = None


class BaseAgent(ABC):
    """
    FDE Agent基类
    设计理念：类型安全、可组合Capability、记忆驱动、工具标准化
    """

    agent_type: str = "base"
    agent_name: str = "Base Agent"
    description: str = "Base agent"

    def __init__(
        self,
        project_id: str,
        model_task: str = "research",
        tools: Optional[list[dict[str, Any]]] = None,
        capabilities: Optional[list[AgentCapability]] = None,
    ):
        self.project_id = project_id
        self.model_task = model_task
        self.tools = tools or []
        self.settings = get_settings()
        self.memory: MemoryManager = get_memory_manager(project_id)
        self.llm: LLMClient = get_llm_client(project_id)
        self.agent_id = str(uuid.uuid4())
        self.conversation_history: list[dict[str, str]] = []
        self._capabilities = capabilities or self._default_capabilities()

    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        ...

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        """执行Agent主逻辑"""
        ...

    async def _call_llm(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        response_json: bool = False,
        required_keys: Optional[list[str]] = None,
        max_retries: int = 1,
    ) -> tuple[str, dict]:
        """
        调用LLM的统一入口（v0.1.2 B3：schema校验+失败自动重试）

        Args:
            required_keys: parsed_json 必须包含的顶层字段（缺失触发重试）
            max_retries: 校验失败后的重试次数（重试时附带缺失字段提示）

        Returns:
            (content_text, parsed_json_dict)
        """
        if system_prompt is None:
            system_prompt = self.get_system_prompt()
        if model is None:
            model = self.settings.get_model_for_task(self.model_task)[0]

        messages = [
            LLMMessage("system", system_prompt),
            LLMMessage("user", user_prompt),
        ]

        if not response_json:
            response = await self.llm.chat(
                messages=messages,
                model=model,
                temperature=temperature,
            )
            return response.content, {}

        attempt = 0
        while True:
            response, parsed = await self.llm.chat_json(
                messages=messages,
                model=model,
                temperature=temperature,
            )
            missing = [k for k in (required_keys or []) if k not in parsed] if parsed else (required_keys or [])
            if parsed and not missing:
                return response.content, parsed
            if attempt >= max_retries:
                # 重试仍失败：返回已有解析结果（调用方用mock兜底补齐）
                return response.content, parsed
            attempt += 1
            # 带错误反馈重试，并显式附schema提示
            feedback = (
                f"你上次的输出缺少必需字段：{missing}。"
                f"请重新输出完整JSON，必须包含全部字段：{required_keys}。只输出JSON，不要其他文字。"
            )
            messages.append(LLMMessage("assistant", response.content[:2000]))
            messages.append(LLMMessage("user", feedback))

    def _has_real_llm(self) -> bool:
        """检查是否配置了真实LLM API Key（v0.3.0：custom/openai/ollama 兼容端点同样视为真实）"""
        if self.settings.llm_provider in ("openai", "ollama", "custom"):
            return bool(self.settings.local_model_base_url)
        return bool(self.settings.deepseek_api_key or self.settings.qwen_api_key)

    def _default_capabilities(self) -> list[AgentCapability]:
        """默认注入的横切能力"""
        return [
            AgentCapability(
                name="memory_injection",
                description="自动注入项目记忆到上下文",
                before_run=self._inject_memory,
            ),
            AgentCapability(
                name="output_validation",
                description="输出结果校验",
                after_run=self._validate_output,
            ),
            AgentCapability(
                name="observability",
                description="执行追踪与日志",
                before_run=self._log_start,
                after_run=self._log_end,
            ),
        ]

    async def _inject_memory(self, agent: "BaseAgent", input_data: dict[str, Any]) -> None:
        """运行前注入项目记忆"""
        try:
            context = await self.memory.get_project_context()
            if context:
                input_data["_memory_context"] = context
        except Exception as e:
            # 记忆注入失败不阻断主流程
            input_data["_memory_context"] = f"[记忆加载失败: {e}]"

    async def _validate_output(self, agent: "BaseAgent", result: AgentResult) -> AgentResult:
        """输出结果校验"""
        if not result.success:
            return result
        # 基础校验：非空
        if not result.content and not result.structured_output:
            result.success = False
            result.error = "Agent输出为空"
        # 结构化输出校验（如果有）
        if result.structured_output:
            try:
                json.dumps(result.structured_output, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                result.metadata["output_validation_warning"] = f"结构化输出不可序列化: {e}"
        return result

    async def _log_start(self, agent: "BaseAgent", input_data: dict[str, Any]) -> None:
        """记录开始"""
        self._start_time = time.time()

    async def _log_end(self, agent: "BaseAgent", result: AgentResult) -> AgentResult:
        """记录结束"""
        if hasattr(self, "_start_time"):
            result.duration_seconds = round(time.time() - self._start_time, 3)
        result.metadata.update(
            {
                "agent_type": self.agent_type,
                "agent_name": self.agent_name,
                "agent_id": self.agent_id,
                "project_id": self.project_id,
            }
        )
        return result

    async def _execute_with_capabilities(self, input_data: dict[str, Any]) -> AgentResult:
        """带Capability钩子的执行流程"""
        # before_run钩子
        for cap in self._capabilities:
            if cap.before_run:
                try:
                    await cap.before_run(self, input_data)
                except Exception as e:
                    input_data.setdefault("_capability_warnings", []).append(f"{cap.name}.before_run failed: {e}")

        try:
            result = await self.run(input_data)
        except Exception as e:
            # on_error钩子
            for cap in self._capabilities:
                if cap.on_error:
                    try:
                        fallback = await cap.on_error(self, e)
                        if fallback:
                            result = fallback
                            break
                    except Exception:
                        pass
            else:
                result = AgentResult(
                    success=False,
                    error=f"{type(e).__name__}: {str(e)}",
                    metadata={"exception_type": type(e).__name__},
                )

        # after_run钩子（顺序执行，后一个的输入是前一个的输出）
        for cap in self._capabilities:
            if cap.after_run:
                try:
                    result = await cap.after_run(self, result)
                except Exception as e:
                    result.metadata.setdefault("_capability_warnings", []).append(f"{cap.name}.after_run failed: {e}")

        # 记录到记忆
        if result.success:
            try:
                await self.memory.remember(
                    content=f"[{self.agent_name}] 执行完成: {result.content[:500]}",
                    metadata={"agent_type": self.agent_type, "success": True},
                )
            except Exception:
                pass

        return result

    async def execute(self, input_data: dict[str, Any]) -> AgentResult:
        """对外执行入口"""
        return await self._execute_with_capabilities(input_data)

    def _build_messages(self, user_input: str, system_prompt: Optional[str] = None) -> list[dict[str, str]]:
        """构建对话消息"""
        messages = [{"role": "system", "content": system_prompt or self.get_system_prompt()}]
        # 注入记忆上下文
        if "_memory_context" in self.conversation_history and self.conversation_history:
            pass  # 已在system prompt中处理
        messages.extend(self.conversation_history[-10:])  # 保留最近10轮
        messages.append({"role": "user", "content": user_input})
        return messages

    def _add_to_history(self, role: str, content: str) -> None:
        """添加到对话历史"""
        self.conversation_history.append({"role": role, "content": content})
        # 限制历史长度
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]
