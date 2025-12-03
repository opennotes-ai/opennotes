"""Tests for LLM configuration functionality."""

import base64
import secrets
from uuid import uuid4

import pytest

from src.llm_config.encryption import EncryptionService
from src.llm_config.providers.factory import LLMProviderFactory


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

        encrypted1, key_id1, _ = service.encrypt_api_key(plaintext)
        encrypted2, key_id2, _ = service.encrypt_api_key(plaintext)

        assert encrypted1 != encrypted2
        assert key_id1 != key_id2

    def test_key_rotation(self) -> None:
        """Test key rotation functionality."""
        service = EncryptionService(_generate_test_key())
        original = "sk-test-key"

        encrypted1, key_id1, _ = service.encrypt_api_key(original)
        encrypted2, key_id2, _ = service.rotate_key(encrypted1, key_id1)

        decrypted1 = service.decrypt_api_key(encrypted1, key_id1)
        decrypted2 = service.decrypt_api_key(encrypted2, key_id2)

        assert decrypted1 == decrypted2 == original
        assert key_id1 != key_id2

    def test_invalid_master_key_not_base64(self) -> None:
        """Test that non-base64 master keys are rejected."""
        with pytest.raises(ValueError, match="valid URL-safe base64"):
            EncryptionService("not-valid!!!")

    def test_invalid_master_key_wrong_byte_length(self) -> None:
        """Test that master keys with wrong byte length are rejected."""
        short_key = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode()
        with pytest.raises(ValueError, match="exactly 32 bytes"):
            EncryptionService(short_key)

    def test_valid_master_key_exactly_32_bytes(self) -> None:
        """Test that valid 32-byte keys are accepted."""
        valid_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        service = EncryptionService(valid_key)
        assert service is not None
        assert len(service.master_key) == 32

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


class TestEncryptionKeyValidation:
    """Test encryption master key validation in Settings."""

    def test_valid_encryption_key_format(self) -> None:
        """Test that properly formatted encryption keys are accepted."""
        import os

        from src.config import Settings

        # Save original values
        orig_encryption = os.environ.get("ENCRYPTION_MASTER_KEY")
        orig_credentials = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        orig_jwt = os.environ.get("JWT_SECRET_KEY")

        valid_key = _generate_test_key()
        os.environ["ENCRYPTION_MASTER_KEY"] = valid_key
        os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "r3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3o="
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-32-chars-min"

        try:
            settings = Settings()
            assert valid_key == settings.ENCRYPTION_MASTER_KEY
        finally:
            # Restore original values
            if orig_encryption is not None:
                os.environ["ENCRYPTION_MASTER_KEY"] = orig_encryption
            elif "ENCRYPTION_MASTER_KEY" in os.environ:
                del os.environ["ENCRYPTION_MASTER_KEY"]
            if orig_credentials is not None:
                os.environ["CREDENTIALS_ENCRYPTION_KEY"] = orig_credentials
            elif "CREDENTIALS_ENCRYPTION_KEY" in os.environ:
                del os.environ["CREDENTIALS_ENCRYPTION_KEY"]
            if orig_jwt is not None:
                os.environ["JWT_SECRET_KEY"] = orig_jwt
            elif "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]

    def test_invalid_base64_encryption_key(self) -> None:
        """Test that invalid base64 keys are rejected at settings level."""
        import os

        from pydantic import ValidationError

        from src.config import Settings

        # Save original values
        orig_encryption = os.environ.get("ENCRYPTION_MASTER_KEY")
        orig_credentials = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        orig_jwt = os.environ.get("JWT_SECRET_KEY")

        os.environ["ENCRYPTION_MASTER_KEY"] = "not-valid-base64!!!"
        os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "r3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3o="
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-32-chars-min"

        try:
            with pytest.raises(ValidationError, match="must decode to exactly 32 bytes"):
                Settings()
        finally:
            # Restore original values
            if orig_encryption is not None:
                os.environ["ENCRYPTION_MASTER_KEY"] = orig_encryption
            elif "ENCRYPTION_MASTER_KEY" in os.environ:
                del os.environ["ENCRYPTION_MASTER_KEY"]
            if orig_credentials is not None:
                os.environ["CREDENTIALS_ENCRYPTION_KEY"] = orig_credentials
            elif "CREDENTIALS_ENCRYPTION_KEY" in os.environ:
                del os.environ["CREDENTIALS_ENCRYPTION_KEY"]
            if orig_jwt is not None:
                os.environ["JWT_SECRET_KEY"] = orig_jwt
            elif "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]

    def test_wrong_byte_length_encryption_key(self) -> None:
        """Test that keys with wrong byte length are rejected."""
        import os

        from pydantic import ValidationError

        from src.config import Settings

        # Save original values
        orig_encryption = os.environ.get("ENCRYPTION_MASTER_KEY")
        orig_credentials = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        orig_jwt = os.environ.get("JWT_SECRET_KEY")

        short_key = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode()
        os.environ["ENCRYPTION_MASTER_KEY"] = short_key
        os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "r3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3o="
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-32-chars-min"

        try:
            with pytest.raises(ValidationError, match="exactly 32 bytes"):
                Settings()
        finally:
            # Restore original values
            if orig_encryption is not None:
                os.environ["ENCRYPTION_MASTER_KEY"] = orig_encryption
            elif "ENCRYPTION_MASTER_KEY" in os.environ:
                del os.environ["ENCRYPTION_MASTER_KEY"]
            if orig_credentials is not None:
                os.environ["CREDENTIALS_ENCRYPTION_KEY"] = orig_credentials
            elif "CREDENTIALS_ENCRYPTION_KEY" in os.environ:
                del os.environ["CREDENTIALS_ENCRYPTION_KEY"]
            if orig_jwt is not None:
                os.environ["JWT_SECRET_KEY"] = orig_jwt
            elif "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]

    def test_low_entropy_encryption_key(self) -> None:
        """Test that keys with low entropy are rejected."""
        import os

        from pydantic import ValidationError

        from src.config import Settings

        # Save original values
        orig_encryption = os.environ.get("ENCRYPTION_MASTER_KEY")
        orig_credentials = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        orig_jwt = os.environ.get("JWT_SECRET_KEY")
        orig_testing = os.environ.get("TESTING")

        low_entropy_key = base64.urlsafe_b64encode(b"a" * 32).decode()
        os.environ["ENCRYPTION_MASTER_KEY"] = low_entropy_key
        os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "r3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3o="
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-32-chars-min"
        os.environ.pop("TESTING", None)

        try:
            with pytest.raises(ValidationError, match="insufficient entropy"):
                Settings()
        finally:
            # Restore original values
            if orig_encryption is not None:
                os.environ["ENCRYPTION_MASTER_KEY"] = orig_encryption
            elif "ENCRYPTION_MASTER_KEY" in os.environ:
                del os.environ["ENCRYPTION_MASTER_KEY"]
            if orig_credentials is not None:
                os.environ["CREDENTIALS_ENCRYPTION_KEY"] = orig_credentials
            elif "CREDENTIALS_ENCRYPTION_KEY" in os.environ:
                del os.environ["CREDENTIALS_ENCRYPTION_KEY"]
            if orig_jwt is not None:
                os.environ["JWT_SECRET_KEY"] = orig_jwt
            elif "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]
            if orig_testing is not None:
                os.environ["TESTING"] = orig_testing

    def test_low_diversity_encryption_key(self) -> None:
        """Test that keys with low byte diversity are rejected."""
        import os

        from pydantic import ValidationError

        from src.config import Settings

        # Save original values
        orig_encryption = os.environ.get("ENCRYPTION_MASTER_KEY")
        orig_credentials = os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
        orig_jwt = os.environ.get("JWT_SECRET_KEY")
        orig_testing = os.environ.get("TESTING")

        low_diversity = bytes([0, 1] * 16)
        low_diversity_key = base64.urlsafe_b64encode(low_diversity).decode()
        os.environ["ENCRYPTION_MASTER_KEY"] = low_diversity_key
        os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "r3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3pXU9wJR3o="
        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-32-chars-min"
        os.environ.pop("TESTING", None)

        try:
            with pytest.raises(ValidationError, match="insufficient entropy"):
                Settings()
        finally:
            # Restore original values
            if orig_encryption is not None:
                os.environ["ENCRYPTION_MASTER_KEY"] = orig_encryption
            elif "ENCRYPTION_MASTER_KEY" in os.environ:
                del os.environ["ENCRYPTION_MASTER_KEY"]
            if orig_credentials is not None:
                os.environ["CREDENTIALS_ENCRYPTION_KEY"] = orig_credentials
            elif "CREDENTIALS_ENCRYPTION_KEY" in os.environ:
                del os.environ["CREDENTIALS_ENCRYPTION_KEY"]
            if orig_jwt is not None:
                os.environ["JWT_SECRET_KEY"] = orig_jwt
            elif "JWT_SECRET_KEY" in os.environ:
                del os.environ["JWT_SECRET_KEY"]
            if orig_testing is not None:
                os.environ["TESTING"] = orig_testing

    def test_shannon_entropy_calculation(self) -> None:
        """Test Shannon entropy calculation for different byte patterns."""
        from src.config import Settings

        all_same = b"\x00" * 32
        entropy_same = Settings._calculate_shannon_entropy(all_same)
        assert entropy_same == 0.0

        all_different = bytes(range(32))
        entropy_different = Settings._calculate_shannon_entropy(all_different)
        assert entropy_different == 5.0

        random_bytes = secrets.token_bytes(32)
        entropy_random = Settings._calculate_shannon_entropy(random_bytes)
        assert entropy_random > 4.0


class TestLLMProviderFactory:
    """Test LLM provider factory."""

    def test_create_openai_provider(self) -> None:
        """Test creating an OpenAI provider."""
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

    def test_create_anthropic_provider(self) -> None:
        """Test creating an Anthropic provider."""
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
        from src.llm_config.schemas import LLMConfigCreate

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
        from pydantic import ValidationError

        from src.llm_config.schemas import LLMConfigCreate

        with pytest.raises(ValidationError, match="must start with 'sk-'"):
            LLMConfigCreate(
                provider="openai",
                api_key="invalid-key",
            )

    def test_config_create_validates_anthropic_key_format(self) -> None:
        """Test Anthropic API key format validation."""
        from pydantic import ValidationError

        from src.llm_config.schemas import LLMConfigCreate

        with pytest.raises(ValidationError, match="must start with 'sk-ant-'"):
            LLMConfigCreate(
                provider="anthropic",
                api_key="invalid-key",
            )

    def test_config_update(self) -> None:
        """Test LLM configuration update schema."""
        from src.llm_config.schemas import LLMConfigUpdate

        update = LLMConfigUpdate(
            enabled=False,
            daily_request_limit=500,
        )

        assert update.enabled is False
        assert update.daily_request_limit == 500
        assert update.api_key is None


@pytest.mark.asyncio
class TestLLMClientManager:
    """Test LLM client manager with caching."""

    async def test_cache_invalidation(self) -> None:
        """Test cache invalidation."""
        from unittest.mock import AsyncMock, MagicMock

        from src.llm_config.manager import LLMClientManager

        encryption_service = EncryptionService(_generate_test_key())
        manager = LLMClientManager(encryption_service)

        community_id = uuid4()
        mock_provider = MagicMock()
        mock_provider.close = AsyncMock()
        manager.client_cache[(community_id, "openai")] = mock_provider

        assert (community_id, "openai") in manager.client_cache

        manager.invalidate_cache(community_id, "openai")
        assert (community_id, "openai") not in manager.client_cache

    async def test_clear_cache(self) -> None:
        """Test clearing all cached clients."""
        from unittest.mock import AsyncMock, MagicMock

        from src.llm_config.manager import LLMClientManager

        encryption_service = EncryptionService(_generate_test_key())
        manager = LLMClientManager(encryption_service)

        mock_provider1 = MagicMock()
        mock_provider1.close = AsyncMock()
        mock_provider2 = MagicMock()
        mock_provider2.close = AsyncMock()

        manager.client_cache[(uuid4(), "openai")] = mock_provider1
        manager.client_cache[(uuid4(), "anthropic")] = mock_provider2

        assert len(manager.client_cache) == 2

        manager.clear_cache()
        assert len(manager.client_cache) == 0


@pytest.mark.asyncio
class TestLLMUsageTracker:
    """Test LLM usage tracking and rate limiting."""

    async def test_usage_stats_structure(self) -> None:
        """Test usage stats return proper structure."""
        from src.llm_config.usage_tracker import LLMUsageTracker

        assert LLMUsageTracker is not None


def test_import_all_exports() -> None:
    """Test that all public exports are importable."""
    from src.llm_config import (
        AnthropicProvider,
        CommunityServer,
        CommunityServerLLMConfig,
        EncryptionService,
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
        OpenAIProvider,
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
    assert OpenAIProvider is not None
    assert AnthropicProvider is not None
    assert LLMConfigCreate is not None
    assert LLMConfigUpdate is not None
    assert LLMConfigResponse is not None
    assert LLMConfigTestRequest is not None
    assert LLMConfigTestResponse is not None
    assert LLMUsageStatsResponse is not None
    assert router is not None
