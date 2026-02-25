"""LLM configuration module for per-community-server API key management."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.llm_config.encryption import EncryptionService
    from src.llm_config.manager import LLMClientManager
    from src.llm_config.models import CommunityServer, CommunityServerLLMConfig, LLMUsageLog
    from src.llm_config.providers import (
        LiteLLMCompletionParams,
        LiteLLMProvider,
        LiteLLMProviderSettings,
        LLMMessage,
        LLMProvider,
        LLMProviderFactory,
        LLMResponse,
    )
    from src.llm_config.router import router
    from src.llm_config.schemas import (
        LLMConfigCreate,
        LLMConfigResponse,
        LLMConfigTestRequest,
        LLMConfigTestResponse,
        LLMConfigUpdate,
        LLMUsageStatsResponse,
    )
    from src.llm_config.secure_string import SecureString, secure_api_key_context
    from src.llm_config.service import LLMService
    from src.llm_config.usage_tracker import LLMUsageLimitExceeded, LLMUsageTracker

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "CommunityServer": ("src.llm_config.models", "CommunityServer"),
    "CommunityServerLLMConfig": ("src.llm_config.models", "CommunityServerLLMConfig"),
    "EncryptionService": ("src.llm_config.encryption", "EncryptionService"),
    "LLMClientManager": ("src.llm_config.manager", "LLMClientManager"),
    "LLMConfigCreate": ("src.llm_config.schemas", "LLMConfigCreate"),
    "LLMConfigResponse": ("src.llm_config.schemas", "LLMConfigResponse"),
    "LLMConfigTestRequest": ("src.llm_config.schemas", "LLMConfigTestRequest"),
    "LLMConfigTestResponse": ("src.llm_config.schemas", "LLMConfigTestResponse"),
    "LLMConfigUpdate": ("src.llm_config.schemas", "LLMConfigUpdate"),
    "LLMMessage": ("src.llm_config.providers", "LLMMessage"),
    "LLMProvider": ("src.llm_config.providers", "LLMProvider"),
    "LLMProviderFactory": ("src.llm_config.providers", "LLMProviderFactory"),
    "LLMResponse": ("src.llm_config.providers", "LLMResponse"),
    "LLMService": ("src.llm_config.service", "LLMService"),
    "LLMUsageLimitExceeded": ("src.llm_config.usage_tracker", "LLMUsageLimitExceeded"),
    "LLMUsageLog": ("src.llm_config.models", "LLMUsageLog"),
    "LLMUsageStatsResponse": ("src.llm_config.schemas", "LLMUsageStatsResponse"),
    "LLMUsageTracker": ("src.llm_config.usage_tracker", "LLMUsageTracker"),
    "LiteLLMCompletionParams": ("src.llm_config.providers", "LiteLLMCompletionParams"),
    "LiteLLMProvider": ("src.llm_config.providers", "LiteLLMProvider"),
    "LiteLLMProviderSettings": ("src.llm_config.providers", "LiteLLMProviderSettings"),
    "SecureString": ("src.llm_config.secure_string", "SecureString"),
    "router": ("src.llm_config.router", "router"),
    "secure_api_key_context": ("src.llm_config.secure_string", "secure_api_key_context"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CommunityServer",
    "CommunityServerLLMConfig",
    "EncryptionService",
    "LLMClientManager",
    "LLMConfigCreate",
    "LLMConfigResponse",
    "LLMConfigTestRequest",
    "LLMConfigTestResponse",
    "LLMConfigUpdate",
    "LLMMessage",
    "LLMProvider",
    "LLMProviderFactory",
    "LLMResponse",
    "LLMService",
    "LLMUsageLimitExceeded",
    "LLMUsageLog",
    "LLMUsageStatsResponse",
    "LLMUsageTracker",
    "LiteLLMCompletionParams",
    "LiteLLMProvider",
    "LiteLLMProviderSettings",
    "SecureString",
    "router",
    "secure_api_key_context",
]
