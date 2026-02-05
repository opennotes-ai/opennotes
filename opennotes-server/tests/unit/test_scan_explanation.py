"""Tests for scan explanation generation."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.llm_config.providers.base import LLMResponse


class TestGenerateScanExplanation:
    """Tests for generate_scan_explanation function."""

    @pytest.mark.asyncio
    async def test_generates_one_sentence_explanation(self) -> None:
        """generate_scan_explanation should return a one-sentence explanation."""
        from src.services.ai_note_writer import AINoteWriter

        mock_llm_service = MagicMock()
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="This message contains a claim that has been fact-checked as false.",
                model="gpt-5-mini",
                tokens_used=50,
                finish_reason="stop",
                provider="openai",
            )
        )

        writer = AINoteWriter(llm_service=mock_llm_service)
        mock_db = MagicMock()
        community_server_id = uuid4()

        original_message = "COVID vaccines contain microchips"
        fact_check_data = {
            "id": str(uuid4()),
            "title": "COVID Vaccines Microchip Claim",
            "content": "This claim has been debunked",
            "rating": "false",
            "source_url": "https://snopes.com/fact-check/123",
            "similarity_score": 0.92,
        }

        explanation = await writer.generate_scan_explanation(
            original_message=original_message,
            fact_check_data=fact_check_data,
            db=mock_db,
            community_server_id=community_server_id,
        )

        assert isinstance(explanation, str)
        assert len(explanation) > 0
        mock_llm_service.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_correct_prompt(self) -> None:
        """generate_scan_explanation should use the specified prompt format."""
        from src.services.ai_note_writer import AINoteWriter

        mock_llm_service = MagicMock()
        mock_llm_service.complete = AsyncMock(
            return_value=LLMResponse(
                content="Explanation text",
                model="gpt-5-mini",
                tokens_used=30,
                finish_reason="stop",
                provider="openai",
            )
        )

        writer = AINoteWriter(llm_service=mock_llm_service)
        mock_db = MagicMock()
        community_server_id = uuid4()

        original_message = "Test message"
        fact_check_data = {
            "id": str(uuid4()),
            "title": "Test Title",
            "content": "Test content",
            "rating": "mostly-false",
            "source_url": "https://example.com",
            "similarity_score": 0.85,
        }

        await writer.generate_scan_explanation(
            original_message=original_message,
            fact_check_data=fact_check_data,
            db=mock_db,
            community_server_id=community_server_id,
        )

        call_args = mock_llm_service.complete.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        user_message = next(m for m in messages if m.role == "user")

        assert "Test message" in user_message.content
        assert "one sentence explanation" in user_message.content.lower()

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self) -> None:
        """generate_scan_explanation should propagate LLM errors."""
        from src.services.ai_note_writer import AINoteWriter

        mock_llm_service = MagicMock()
        mock_llm_service.complete = AsyncMock(side_effect=Exception("LLM service unavailable"))

        writer = AINoteWriter(llm_service=mock_llm_service)
        mock_db = MagicMock()
        community_server_id = uuid4()

        with pytest.raises(Exception, match="LLM service unavailable"):
            await writer.generate_scan_explanation(
                original_message="Test",
                fact_check_data={"id": str(uuid4()), "title": "Test"},
                db=mock_db,
                community_server_id=community_server_id,
            )
