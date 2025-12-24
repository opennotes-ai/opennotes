"""LLM configuration module for per-community-server API key management."""

from typing import TYPE_CHECKING

from src.llm_config.encryption import EncryptionService
from src.llm_config.manager import LLMClientManager
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig, LLMUsageLog
from src.llm_config.providers import (
    LiteLLMProvider,
    LLMMessage,
    LLMProvider,
    LLMProviderFactory,
    LLMResponse,
)
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

if TYPE_CHECKING:
    from src.llm_config.router import router


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
    "LiteLLMProvider",
    "SecureString",
    "router",
    "secure_api_key_context",
]
