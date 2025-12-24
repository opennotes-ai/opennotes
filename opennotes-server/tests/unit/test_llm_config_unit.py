"""Unit tests for LLM configuration (no database required)."""

import base64
import secrets

import pytest
from pydantic import ValidationError

from src.llm_config.encryption import EncryptionService
from src.llm_config.providers.factory import LLMProviderFactory
from src.llm_config.schemas import LLMConfigCreate, LLMConfigUpdate


def _generate_test_key() -> str:
    """Generate a valid test encryption key."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


class TestEncryptionService:
    """Test encryption service functionality."""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test that encryption and decryption work correctly."""
        service = EncryptionService(_generate_test_key())
        original = "sk-test-api-key-12345"

        encrypted, key_id, preview = service.encrypt_api_key(original)
        decrypted = service.decrypt_api_key(encrypted, key_id)

        assert decrypted == original
        assert preview == "...2345"

    def test_different_salts_produce_different_ciphertexts(self) -> None:
        """Test that same plaintext with different salts produces different ciphertexts."""
        service = EncryptionService(_generate_test_key())
        plaintext = "sk-test-key"

        encrypted1, key_id1, preview1 = service.encrypt_api_key(plaintext)
        encrypted2, key_id2, preview2 = service.encrypt_api_key(plaintext)

        assert encrypted1 != encrypted2
        assert key_id1 != key_id2
        assert preview1 == preview2 == "...-key"

    def test_key_rotation(self) -> None:
        """Test key rotation functionality."""
        service = EncryptionService(_generate_test_key())
        original = "sk-test-key"

        encrypted1, key_id1, preview1 = service.encrypt_api_key(original)
        encrypted2, key_id2, preview2 = service.rotate_key(encrypted1, key_id1)

        decrypted1 = service.decrypt_api_key(encrypted1, key_id1)
        decrypted2 = service.decrypt_api_key(encrypted2, key_id2)

        assert decrypted1 == decrypted2 == original
        assert key_id1 != key_id2
        assert preview1 == preview2 == "...-key"

    def test_invalid_master_key_length(self) -> None:
        """Test that short master keys are rejected."""
        with pytest.raises(ValueError, match="must decode to exactly 32 bytes"):
            EncryptionService(base64.urlsafe_b64encode(b"short").decode())

    def test_caching(self) -> None:
        """Test that decryption uses caching."""
        service = EncryptionService(_generate_test_key())
        plaintext = "sk-test-key"

        encrypted, key_id, _ = service.encrypt_api_key(plaintext)

        service.decrypt_api_key(encrypted, key_id)
        assert key_id in service.key_cache

        service.decrypt_api_key(encrypted, key_id)
        assert key_id in service.key_cache

        service.clear_cache()
        assert len(service.key_cache) == 0

    def test_api_key_preview_format(self) -> None:
        """Test that API key preview has correct format."""
        service = EncryptionService(_generate_test_key())

        _, _, preview1 = service.encrypt_api_key("sk-1234567890")
        assert preview1 == "...7890"

        _, _, preview2 = service.encrypt_api_key("abc")
        assert preview2 == "..."

        _, _, preview3 = service.encrypt_api_key("test")
        assert preview3 == "...test"


class TestLLMProviderFactory:
    """Test LLM provider factory."""

    def test_create_openai_provider(self) -> None:
        """Test creating an OpenAI provider via LiteLLM."""
        provider = LLMProviderFactory.create(
            "openai",
            "sk-test-key",
            "gpt-5.1",
            {"temperature": 0.7, "max_tokens": 1000},
        )

        assert provider is not None
        assert provider.api_key == "sk-test-key"
        assert provider.default_model == "gpt-5.1"
        assert provider.settings.temperature == 0.7
        assert provider.settings.max_tokens == 1000

    def test_create_anthropic_provider(self) -> None:
        """Test creating an Anthropic provider via LiteLLM."""
        provider = LLMProviderFactory.create(
            "anthropic",
            "sk-ant-test-key",
            "claude-3-opus-20240229",
            {"temperature": 0.5},
        )

        assert provider is not None
        assert provider.api_key == "sk-ant-test-key"
        assert provider.default_model == "claude-3-opus-20240229"
        assert provider.settings.temperature == 0.5

    def test_unknown_provider(self) -> None:
        """Test that unknown provider raises error."""
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMProviderFactory.create("unknown", "key", "model", {})

    def test_list_providers(self) -> None:
        """Test listing available providers."""
        providers = LLMProviderFactory.list_providers()

        assert "openai" in providers
        assert "anthropic" in providers


class TestLLMConfigSchemas:
    """Test Pydantic schemas for LLM configuration."""

    def test_config_create_valid(self) -> None:
        """Test valid LLM configuration creation."""
        config = LLMConfigCreate(
            provider="openai",
            api_key="sk-test-key",
            enabled=True,
            settings={"default_model": "gpt-5.1"},
            daily_request_limit=1000,
        )

        assert config.provider == "openai"
        assert config.api_key == "sk-test-key"
        assert config.daily_request_limit == 1000

    def test_config_create_validates_openai_key_format(self) -> None:
        """Test OpenAI API key format validation."""
        with pytest.raises(ValidationError, match="must start with 'sk-'"):
            LLMConfigCreate(
                provider="openai",
                api_key="invalid-key",
            )

    def test_config_create_validates_anthropic_key_format(self) -> None:
        """Test Anthropic API key format validation."""
        with pytest.raises(ValidationError, match="must start with 'sk-ant-'"):
            LLMConfigCreate(
                provider="anthropic",
                api_key="invalid-key",
            )

    def test_config_update(self) -> None:
        """Test LLM configuration update schema."""
        update = LLMConfigUpdate(
            enabled=False,
            daily_request_limit=500,
        )

        assert update.enabled is False
        assert update.daily_request_limit == 500
        assert update.api_key is None


def test_import_all_exports() -> None:
    """Test that all public exports are importable."""
    from src.llm_config import (
        CommunityServer,
        CommunityServerLLMConfig,
        EncryptionService,
        LiteLLMProvider,
        LLMClientManager,
        LLMConfigCreate,
        LLMConfigResponse,
        LLMConfigTestRequest,
        LLMConfigTestResponse,
        LLMConfigUpdate,
        LLMMessage,
        LLMProvider,
        LLMProviderFactory,
        LLMResponse,
        LLMUsageLog,
        LLMUsageStatsResponse,
        LLMUsageTracker,
        router,
    )

    assert EncryptionService is not None
    assert CommunityServer is not None
    assert CommunityServerLLMConfig is not None
    assert LLMUsageLog is not None
    assert LLMClientManager is not None
    assert LLMUsageTracker is not None
    assert LLMProvider is not None
    assert LLMMessage is not None
    assert LLMResponse is not None
    assert LLMProviderFactory is not None
    assert LiteLLMProvider is not None
    assert LLMConfigCreate is not None
    assert LLMConfigUpdate is not None
    assert LLMConfigResponse is not None
    assert LLMConfigTestRequest is not None
    assert LLMConfigTestResponse is not None
    assert LLMUsageStatsResponse is not None
    assert router is not None
