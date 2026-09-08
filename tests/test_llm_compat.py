"""
LLM 客户端兼容性测试（v0.3.0：MiniMax 等 OpenAI 兼容端点支持）

源自真实 MiniMax-M2.7 接入过程修复的三个问题：
1. custom/openai/ollama provider 路由（原只认 deepseek/qwen 前缀）
2. 推理模型 <think>...</think> 剥离
3. JSON 输出容错提取（think 残留/杂文本包裹）
"""

from __future__ import annotations

from src.llm.client import LLMClient, LLMResponse, _strip_think


class TestStripThink:
    def test_strips_think_block(self):
        text = "<think>推理过程...</think>正文答案"
        assert _strip_think(text) == "正文答案"

    def test_no_think_passthrough(self):
        assert _strip_think("普通内容") == "普通内容"

    def test_multiline_think(self):
        text = '<think>\n多行\n推理\n</think>\n{"a": 1}'
        assert _strip_think(text) == '{"a": 1}'


class TestParseJsonTolerance:
    def test_parse_after_think(self):
        resp = LLMResponse(model="test", content='<think>让我想想</think>```json\n{"answer": 42}\n```')
        assert resp.parse_json() == {"answer": 42}

    def test_parse_extracts_json_substring(self):
        resp = LLMResponse(model="test", content='好的，结果是 {"answer": "IQC", "score": 0.9} 请查收')
        assert resp.parse_json() == {"answer": "IQC", "score": 0.9}

    def test_parse_invalid_returns_empty(self):
        assert LLMResponse(model="test", content="完全不是JSON").parse_json() == {}


class TestCustomProviderRouting:
    def test_minimax_model_routes_to_local(self, monkeypatch):
        """MiniMax 模型名应路由到 local_model_base_url（原bug：走deepseek空key→mock）"""
        from src.config import get_settings

        settings = get_settings()
        client = LLMClient("route-test")
        base, key, model = client._get_model_config("MiniMax-M2.7")
        assert base == settings.local_model_base_url
        assert key == settings.local_model_api_key
        assert model == "MiniMax-M2.7"

    def test_deepseek_prefix_unchanged(self):
        client = LLMClient("route-test")
        base, _key, model = client._get_model_config("deepseek-v4-pro")
        assert "deepseek" in base
        assert model == "deepseek-v4-pro"

    def test_has_real_llm_custom_provider(self, monkeypatch):
        """custom provider 时 _has_real_llm 应为 True（原bug：恒False→永远mock）"""
        from src.agents.research import ResearchAgent
        from src.config import get_settings

        monkeypatch.setattr(get_settings(), "llm_provider", "custom")
        monkeypatch.setattr(get_settings(), "local_model_base_url", "https://api.example.com/v1")
        monkeypatch.setattr(get_settings(), "deepseek_api_key", "")
        monkeypatch.setattr(get_settings(), "qwen_api_key", "")
        agent = ResearchAgent("has-real-test")
        assert agent._has_real_llm() is True
