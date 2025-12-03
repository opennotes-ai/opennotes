"""Unit tests for LLM config error message sanitization."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm_config.router import SAFE_ERROR_MESSAGES


@pytest.mark.unit
class TestLLMConfigErrorSanitization:
    """Test that error messages don't leak sensitive information."""

    def test_safe_error_messages_defined(self):
        """Test that safe error messages are properly defined."""
        assert "invalid_key" in SAFE_ERROR_MESSAGES
        assert "rate_limit" in SAFE_ERROR_MESSAGES
        assert "network" in SAFE_ERROR_MESSAGES
        assert "permission" in SAFE_ERROR_MESSAGES
        assert "generic" in SAFE_ERROR_MESSAGES

    def test_safe_error_messages_generic(self):
        """Test that safe error messages don't contain sensitive details."""
        for message in SAFE_ERROR_MESSAGES.values():
            # Ensure no provider-specific details
            assert "openai" not in message.lower()
            assert "anthropic" not in message.lower()

            # Ensure no key fragments
            assert "sk-" not in message.lower()
            assert "api_" not in message.lower()

            # Ensure no technical stack traces
            assert "exception" not in message.lower()
            assert "error:" not in message.lower()
            assert "traceback" not in message.lower()


@pytest.mark.unit
class TestCreateLLMConfigErrorHandling:
    """Test error handling in create_llm_config endpoint."""

    @pytest.mark.asyncio
    async def test_value_error_returns_safe_message(self):
        """Test that ValueError returns safe error message."""
        from uuid import uuid4

        from fastapi import HTTPException

        from src.llm_config.router import create_llm_config
        from src.llm_config.schemas import LLMConfigCreate

        community_server_id = uuid4()
        config = LLMConfigCreate(
            provider="openai",
            api_key="sk-test-key",
        )

        # Mock dependencies
        mock_db = AsyncMock()
        mock_encryption = MagicMock()
        mock_membership = MagicMock()

        # Mock database to return community server (first call) and None for existing config (second call)
        mock_result_server = MagicMock()
        mock_result_server.scalar_one_or_none.return_value = MagicMock(id=community_server_id)
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = None  # No existing config
        mock_db.execute = AsyncMock(side_effect=[mock_result_server, mock_result_existing])

        # Mock LLMProviderFactory to raise ValueError
        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            mock_create.side_effect = ValueError("Invalid API key format: expected sk-proj-...")

            with pytest.raises(HTTPException) as exc_info:
                await create_llm_config(
                    community_server_id,
                    config,
                    mock_db,
                    mock_encryption,
                    mock_membership,
                )

            # Should return safe message, not the detailed error
            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == SAFE_ERROR_MESSAGES["invalid_key"]
            assert "sk-proj-" not in exc_info.value.detail  # No key fragment leaked

    @pytest.mark.asyncio
    async def test_connection_error_returns_safe_message(self):
        """Test that ConnectionError returns safe error message."""
        from uuid import uuid4

        from fastapi import HTTPException

        from src.llm_config.router import create_llm_config
        from src.llm_config.schemas import LLMConfigCreate

        community_server_id = uuid4()
        config = LLMConfigCreate(
            provider="openai",
            api_key="sk-test-key",
        )

        mock_db = AsyncMock()
        mock_encryption = MagicMock()
        mock_membership = MagicMock()

        mock_result_server = MagicMock()
        mock_result_server.scalar_one_or_none.return_value = MagicMock(id=community_server_id)
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[mock_result_server, mock_result_existing])

        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            mock_create.side_effect = ConnectionError("Connection refused to api.openai.com:443")

            with pytest.raises(HTTPException) as exc_info:
                await create_llm_config(
                    community_server_id,
                    config,
                    mock_db,
                    mock_encryption,
                    mock_membership,
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == SAFE_ERROR_MESSAGES["network"]
            assert "api.openai.com" not in exc_info.value.detail  # No endpoint leaked

    @pytest.mark.asyncio
    async def test_generic_exception_returns_safe_message(self):
        """Test that unexpected exceptions return generic safe message."""
        from uuid import uuid4

        from fastapi import HTTPException

        from src.llm_config.router import create_llm_config
        from src.llm_config.schemas import LLMConfigCreate

        community_server_id = uuid4()
        config = LLMConfigCreate(
            provider="openai",
            api_key="sk-test-key",
        )

        mock_db = AsyncMock()
        mock_encryption = MagicMock()
        mock_membership = MagicMock()

        mock_result_server = MagicMock()
        mock_result_server.scalar_one_or_none.return_value = MagicMock(id=community_server_id)
        mock_result_existing = MagicMock()
        mock_result_existing.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(side_effect=[mock_result_server, mock_result_existing])

        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            # Simulate an unexpected exception with sensitive details
            mock_create.side_effect = RuntimeError(
                "Rate limit exceeded for organization org-abc123. API key: sk-proj-xyz..."
            )

            with pytest.raises(HTTPException) as exc_info:
                await create_llm_config(
                    community_server_id,
                    config,
                    mock_db,
                    mock_encryption,
                    mock_membership,
                )

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == SAFE_ERROR_MESSAGES["generic"]
            # Ensure no sensitive details leaked
            assert "org-abc123" not in exc_info.value.detail
            assert "sk-proj-" not in exc_info.value.detail


@pytest.mark.unit
class TestTestLLMConfigErrorHandling:
    """Test error handling in test_llm_config endpoint."""

    @pytest.mark.asyncio
    async def test_value_error_returns_safe_message(self):
        """Test that ValueError in test endpoint returns safe message."""
        from uuid import uuid4

        from src.llm_config.router import test_llm_config
        from src.llm_config.schemas import LLMConfigTestRequest

        community_server_id = uuid4()
        test_request = LLMConfigTestRequest(
            provider="openai",
            api_key="invalid-key",
            settings={},
        )
        mock_membership = MagicMock()

        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            mock_create.side_effect = ValueError("Invalid key format: expected sk-...")

            response = await test_llm_config(
                community_server_id,
                test_request,
                mock_membership,
            )

            assert response.valid is False
            assert response.error_message == SAFE_ERROR_MESSAGES["invalid_key"]
            assert "sk-..." not in response.error_message

    @pytest.mark.asyncio
    async def test_connection_error_returns_safe_message(self):
        """Test that ConnectionError in test endpoint returns safe message."""
        from uuid import uuid4

        from src.llm_config.router import test_llm_config
        from src.llm_config.schemas import LLMConfigTestRequest

        community_server_id = uuid4()
        test_request = LLMConfigTestRequest(
            provider="anthropic",
            api_key="sk-ant-test",
            settings={},
        )
        mock_membership = MagicMock()

        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            mock_create.side_effect = ConnectionError("Timeout connecting to api.anthropic.com")

            response = await test_llm_config(
                community_server_id,
                test_request,
                mock_membership,
            )

            assert response.valid is False
            assert response.error_message == SAFE_ERROR_MESSAGES["network"]
            assert "anthropic.com" not in response.error_message

    @pytest.mark.asyncio
    async def test_generic_exception_returns_safe_message(self):
        """Test that unexpected exceptions return generic safe message."""
        from uuid import uuid4

        from src.llm_config.router import test_llm_config
        from src.llm_config.schemas import LLMConfigTestRequest

        community_server_id = uuid4()
        test_request = LLMConfigTestRequest(
            provider="openai",
            api_key="sk-test-key",
            settings={},
        )
        mock_membership = MagicMock()

        with patch("src.llm_config.router.LLMProviderFactory.create") as mock_create:
            mock_create.side_effect = Exception(
                "Internal error: API key sk-test-key is invalid for org-xyz"
            )

            response = await test_llm_config(
                community_server_id,
                test_request,
                mock_membership,
            )

            assert response.valid is False
            assert response.error_message == SAFE_ERROR_MESSAGES["generic"]
            # Ensure sensitive details not leaked
            assert "sk-test-key" not in response.error_message
            assert "org-xyz" not in response.error_message
