"""
扩展点测试（v0.1.1 A5）：插件注册器 + 认证抽象
"""

from __future__ import annotations

import pytest

from src.extensions import PluginInfo, get_registry, reset_registry
from src.extensions.auth import AuthProvider, NoopAuth, Principal, get_auth_provider


class TestPluginRegistry:
    def setup_method(self):
        reset_registry()

    def test_default_edition_is_community(self):
        assert get_registry().edition == "community"

    def test_register_and_capability(self):
        registry = get_registry()
        registry.register(
            PluginInfo(
                name="team-edition",
                version="1.0.0",
                provider="team",
                capabilities=["multi_user", "team_memory"],
            )
        )
        assert registry.edition == "team"
        assert registry.has_capability("team_memory")
        assert not registry.has_capability("sso")

    def test_enterprise_overrides_edition(self):
        registry = get_registry()
        registry.register(PluginInfo(name="te", version="1.0", provider="team"))
        registry.register(PluginInfo(name="ee", version="1.0", provider="enterprise"))
        assert registry.edition == "enterprise"

    def test_duplicate_register_raises(self):
        registry = get_registry()
        registry.register(PluginInfo(name="te", version="1.0"))
        with pytest.raises(ValueError, match="已注册"):
            registry.register(PluginInfo(name="te", version="2.0"))

    def test_unregister(self):
        registry = get_registry()
        registry.register(PluginInfo(name="te", version="1.0"))
        assert registry.unregister("te") is True
        assert registry.unregister("te") is False
        assert registry.get("te") is None


class TestAuthProvider:
    def setup_method(self):
        reset_registry()

    def test_noop_auth_returns_principal(self):
        provider = NoopAuth()
        assert provider.allow_anonymous is True
        assert isinstance(provider, AuthProvider)

    def test_default_provider_is_noop(self):
        assert isinstance(get_auth_provider(), NoopAuth)

    async def test_noop_authenticate(self):
        provider = NoopAuth()
        principal = await provider.authenticate(request=None)
        assert principal.role == "admin"

    def test_principal_permissions(self):
        p = Principal(user_id="u1", role="fde", permissions=["read", "write"])
        assert p.has_permission("read")
        assert not p.has_permission("delete")

    def test_plugin_injects_custom_auth(self):
        class TeamAuth(NoopAuth):
            @property
            def allow_anonymous(self) -> bool:
                return False

        registry = get_registry()
        plugin = PluginInfo(name="team-edition", version="1.0.0", provider="team")
        plugin.hooks["auth_provider"] = TeamAuth()
        registry.register(plugin)
        provider = get_auth_provider()
        assert provider.allow_anonymous is False  # TE 拒绝匿名
