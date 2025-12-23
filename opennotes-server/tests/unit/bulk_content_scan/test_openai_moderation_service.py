"""Tests for OpenAI moderation service."""

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest


@dataclass
class MockCategories:
    """Mock categories object matching OpenAI response structure."""

    violence: bool = False
    violence_graphic: bool = False
    sexual: bool = False
    sexual_minors: bool = False
    hate: bool = False
    hate_threatening: bool = False
    harassment: bool = False
    harassment_threatening: bool = False
    self_harm: bool = False
    self_harm_intent: bool = False
    self_harm_instructions: bool = False
    illicit: bool = False
    illicit_violent: bool = False


@dataclass
class MockCategoryScores:
    """Mock category scores object matching OpenAI response structure."""

    violence: float = 0.0
    violence_graphic: float = 0.0
    sexual: float = 0.0
    sexual_minors: float = 0.0
    hate: float = 0.0
    hate_threatening: float = 0.0
    harassment: float = 0.0
    harassment_threatening: float = 0.0
    self_harm: float = 0.0
    self_harm_intent: float = 0.0
    self_harm_instructions: float = 0.0
    illicit: float = 0.0
    illicit_violent: float = 0.0


@dataclass
class MockModerationResult:
    """Mock moderation result from OpenAI."""

    flagged: bool
    categories: MockCategories
    category_scores: MockCategoryScores


@dataclass
class MockModerationResponse:
    """Mock response from OpenAI moderations.create()."""

    results: list[MockModerationResult]


class TestOpenAIModerationService:
    """Tests for the OpenAI moderation service."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI async client."""
        client = AsyncMock()
        client.moderations = AsyncMock()
        client.moderations.create = AsyncMock()
        return client

    @pytest.fixture
    def moderation_service(self, mock_openai_client):
        """Create moderation service with mock client."""
        from src.bulk_content_scan.openai_moderation_service import OpenAIModerationService

        return OpenAIModerationService(client=mock_openai_client)

    def test_service_exists(self):
        """OpenAIModerationService class should exist."""
        from src.bulk_content_scan.openai_moderation_service import OpenAIModerationService

        assert OpenAIModerationService is not None

    @pytest.mark.asyncio
    async def test_moderate_text_calls_openai_api(self, moderation_service, mock_openai_client):
        """moderate_text should call OpenAI moderations API with text input."""
        mock_response = MockModerationResponse(
            results=[
                MockModerationResult(
                    flagged=False,
                    categories=MockCategories(violence=False, sexual=False),
                    category_scores=MockCategoryScores(violence=0.01, sexual=0.02),
                )
            ]
        )
        mock_openai_client.moderations.create.return_value = mock_response

        await moderation_service.moderate_text("Hello, world!")

        mock_openai_client.moderations.create.assert_called_once()
        call_kwargs = mock_openai_client.moderations.create.call_args.kwargs
        assert call_kwargs["model"] == "omni-moderation-latest"
        assert "Hello, world!" in str(call_kwargs["input"])

    @pytest.mark.asyncio
    async def test_moderate_text_returns_result(self, moderation_service, mock_openai_client):
        """moderate_text should return ModerationResult with flagged status and scores."""
        mock_response = MockModerationResponse(
            results=[
                MockModerationResult(
                    flagged=True,
                    categories=MockCategories(violence=True, sexual=False),
                    category_scores=MockCategoryScores(violence=0.95, sexual=0.02),
                )
            ]
        )
        mock_openai_client.moderations.create.return_value = mock_response

        result = await moderation_service.moderate_text("violent content")

        assert result.flagged is True
        assert result.categories["violence"] is True
        assert result.scores["violence"] == 0.95

    @pytest.mark.asyncio
    async def test_moderate_image_calls_openai_api(self, moderation_service, mock_openai_client):
        """moderate_image should call OpenAI moderations API with image URL."""
        mock_response = MockModerationResponse(
            results=[
                MockModerationResult(
                    flagged=False,
                    categories=MockCategories(violence=False, sexual=False),
                    category_scores=MockCategoryScores(violence=0.01, sexual=0.02),
                )
            ]
        )
        mock_openai_client.moderations.create.return_value = mock_response

        await moderation_service.moderate_image("https://example.com/image.jpg")

        mock_openai_client.moderations.create.assert_called_once()
        call_kwargs = mock_openai_client.moderations.create.call_args.kwargs
        assert call_kwargs["model"] == "omni-moderation-latest"

    @pytest.mark.asyncio
    async def test_moderate_multimodal_text_and_images(
        self, moderation_service, mock_openai_client
    ):
        """moderate_multimodal should handle text and images together."""
        mock_response = MockModerationResponse(
            results=[
                MockModerationResult(
                    flagged=True,
                    categories=MockCategories(violence=True, sexual=False),
                    category_scores=MockCategoryScores(violence=0.85, sexual=0.02),
                )
            ]
        )
        mock_openai_client.moderations.create.return_value = mock_response

        result = await moderation_service.moderate_multimodal(
            text="Check this image",
            image_urls=["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
        )

        mock_openai_client.moderations.create.assert_called_once()
        assert result.flagged is True


class TestModerationResult:
    """Tests for the ModerationResult dataclass."""

    def test_moderation_result_exists(self):
        """ModerationResult should exist and be importable."""
        from src.bulk_content_scan.openai_moderation_service import ModerationResult

        assert ModerationResult is not None

    def test_moderation_result_has_required_fields(self):
        """ModerationResult should have flagged, categories, scores, and max_score fields."""
        from src.bulk_content_scan.openai_moderation_service import ModerationResult

        result = ModerationResult(
            flagged=True,
            categories={"violence": True, "sexual": False},
            scores={"violence": 0.95, "sexual": 0.02},
            max_score=0.95,
            flagged_categories=["violence"],
        )

        assert result.flagged is True
        assert result.categories["violence"] is True
        assert result.scores["violence"] == 0.95
        assert result.max_score == 0.95
        assert "violence" in result.flagged_categories
