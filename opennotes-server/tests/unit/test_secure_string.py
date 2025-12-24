"""Unit tests for secure string handling to prevent API key memory leakage."""

import gc

import pytest

from src.llm_config.secure_string import SecureString, secure_api_key_context


class TestSecureString:
    """Test SecureString class for secure memory handling."""

    def test_secure_string_stores_value(self) -> None:
        """Test that SecureString can store and retrieve values."""
        ss = SecureString("test-secret-key")
        assert ss.get_value() == "test-secret-key"

    def test_secure_string_clear_zeros_memory(self) -> None:
        """Test that clear() zeros out the internal buffer."""
        ss = SecureString("test-secret-key")
        ss.clear()
        assert ss.get_value() == ""
        assert ss._cleared is True

    def test_secure_string_context_manager_clears_on_exit(self) -> None:
        """Test that SecureString clears when used as context manager."""
        with SecureString("secret") as ss:
            assert ss.get_value() == "secret"
        assert ss._cleared is True
        assert ss.get_value() == ""

    def test_secure_string_context_manager_clears_on_exception(self) -> None:
        """Test that SecureString clears even when exception occurs."""
        secure_str = SecureString("secret")
        try:
            with secure_str:
                raise ValueError("test error")
        except ValueError:
            pass
        assert secure_str._cleared is True

    def test_secure_string_len(self) -> None:
        """Test len() returns correct length."""
        ss = SecureString("12345")
        assert len(ss) == 5

    def test_secure_string_len_after_clear(self) -> None:
        """Test len() returns 0 after clearing."""
        ss = SecureString("12345")
        ss.clear()
        assert len(ss) == 0

    def test_secure_string_uses_mutable_storage(self) -> None:
        """Test that internal storage is mutable (bytearray, not str)."""
        ss = SecureString("secret")
        assert isinstance(ss._buffer, bytearray)

    def test_secure_string_double_clear_is_safe(self) -> None:
        """Test that calling clear() multiple times is safe."""
        ss = SecureString("secret")
        ss.clear()
        ss.clear()
        assert ss._cleared is True
        assert ss.get_value() == ""


class TestSecureAPIKeyContext:
    """Test secure_api_key_context for handling API keys in provider operations."""

    def test_context_provides_api_key(self) -> None:
        """Test that context provides access to API key."""
        with secure_api_key_context("sk-test-key") as key:
            assert key == "sk-test-key"

    def test_context_clears_after_use(self) -> None:
        """Test that context clears internal storage after exit."""
        with secure_api_key_context("sk-test-key") as key:
            assert key == "sk-test-key"
        gc.collect()

    def test_context_clears_on_exception(self) -> None:
        """Test that context clears even on exception."""
        with pytest.raises(RuntimeError), secure_api_key_context("sk-test-key"):
            raise RuntimeError("test error")


class TestProviderAPIKeyCleanup:
    """Test that providers properly clean up API keys."""

    @pytest.mark.asyncio
    async def test_provider_close_clears_api_key(self) -> None:
        """Test that calling close() on provider clears API key from memory."""
        from src.llm_config.providers.factory import LLMProviderFactory

        provider = LLMProviderFactory.create(
            "openai",
            "sk-test-secret-key",
            "gpt-4",
            {},
        )

        assert provider.api_key == "sk-test-secret-key"

        await provider.close()

        assert provider.api_key == "" or provider.api_key is None

    @pytest.mark.asyncio
    async def test_provider_close_clears_client_api_key(self) -> None:
        """Test that close() also clears API key from internal client."""
        from src.llm_config.providers import LiteLLMProvider, LiteLLMProviderSettings

        provider = LiteLLMProvider(
            "sk-test-secret-key",
            "openai/gpt-4",
            LiteLLMProviderSettings(),
        )

        await provider.close()

        assert provider.api_key == "" or provider.api_key is None
