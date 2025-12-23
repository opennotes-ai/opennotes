"""Tests for OpenAI moderation integration with BulkContentScanService."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.bulk_content_scan.scan_types import ScanType
from src.bulk_content_scan.schemas import BulkScanMessage, FlaggedMessage


class TestFlaggedMessageModerationFields:
    """Tests for moderation-specific fields in FlaggedMessage schema."""

    def test_flagged_message_accepts_moderation_categories(self):
        """FlaggedMessage should accept optional moderation_categories field."""
        msg = FlaggedMessage(
            message_id="123",
            channel_id="456",
            content="test content",
            author_id="789",
            timestamp=datetime.now(UTC),
            match_score=0.95,
            matched_claim="",
            matched_source="",
            scan_type=ScanType.OPENAI_MODERATION,
            moderation_categories={"violence": True, "sexual": False},
        )
        assert msg.moderation_categories == {"violence": True, "sexual": False}

    def test_flagged_message_accepts_moderation_scores(self):
        """FlaggedMessage should accept optional moderation_scores field."""
        msg = FlaggedMessage(
            message_id="123",
            channel_id="456",
            content="test content",
            author_id="789",
            timestamp=datetime.now(UTC),
            match_score=0.95,
            matched_claim="",
            matched_source="",
            scan_type=ScanType.OPENAI_MODERATION,
            moderation_scores={"violence": 0.95, "sexual": 0.02},
        )
        assert msg.moderation_scores == {"violence": 0.95, "sexual": 0.02}

    def test_flagged_message_accepts_flagged_categories_list(self):
        """FlaggedMessage should accept optional flagged_categories field."""
        msg = FlaggedMessage(
            message_id="123",
            channel_id="456",
            content="test content",
            author_id="789",
            timestamp=datetime.now(UTC),
            match_score=0.95,
            matched_claim="",
            matched_source="",
            scan_type=ScanType.OPENAI_MODERATION,
            flagged_categories=["violence", "harassment"],
        )
        assert msg.flagged_categories == ["violence", "harassment"]

    def test_flagged_message_moderation_fields_optional(self):
        """Moderation fields should be optional for backwards compatibility."""
        msg = FlaggedMessage(
            message_id="123",
            channel_id="456",
            content="test content",
            author_id="789",
            timestamp=datetime.now(UTC),
            match_score=0.8,
            matched_claim="some claim",
            matched_source="http://example.com",
            scan_type=ScanType.SIMILARITY,
        )
        assert msg.moderation_categories is None
        assert msg.moderation_scores is None
        assert msg.flagged_categories is None


class TestScannerDispatch:
    """Tests for scanner dispatch with OPENAI_MODERATION scan type."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_embedding_service(self):
        """Create a mock embedding service."""
        return AsyncMock()

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.lpush = AsyncMock()
        redis.expire = AsyncMock()
        return redis

    @pytest.fixture
    def mock_moderation_service(self):
        """Create a mock OpenAI moderation service."""
        from src.bulk_content_scan.openai_moderation_service import ModerationResult

        service = AsyncMock()
        service.moderate_text = AsyncMock(
            return_value=ModerationResult(
                flagged=True,
                categories={"violence": True, "sexual": False},
                scores={"violence": 0.95, "sexual": 0.02},
                max_score=0.95,
                flagged_categories=["violence"],
            )
        )
        service.moderate_multimodal = AsyncMock(
            return_value=ModerationResult(
                flagged=True,
                categories={"violence": True},
                scores={"violence": 0.85},
                max_score=0.85,
                flagged_categories=["violence"],
            )
        )
        return service

    @pytest.fixture
    def service_with_moderation(
        self, mock_session, mock_embedding_service, mock_redis, mock_moderation_service
    ):
        """Create BulkContentScanService with moderation service."""
        from src.bulk_content_scan.service import BulkContentScanService

        return BulkContentScanService(
            session=mock_session,
            embedding_service=mock_embedding_service,
            redis_client=mock_redis,
            moderation_service=mock_moderation_service,
        )

    @pytest.mark.asyncio
    async def test_run_scanner_dispatches_to_moderation(
        self, service_with_moderation, mock_moderation_service
    ):
        """_run_scanner should dispatch OPENAI_MODERATION to moderation scan."""
        scan_id = uuid4()
        message = BulkScanMessage(
            message_id="123",
            channel_id="456",
            community_server_id="789",
            content="some violent content",
            author_id="user1",
            timestamp=datetime.now(UTC),
        )

        result = await service_with_moderation._run_scanner(
            scan_id, message, "community-platform-id", ScanType.OPENAI_MODERATION
        )

        assert result is not None
        assert result.scan_type == ScanType.OPENAI_MODERATION
        mock_moderation_service.moderate_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_moderation_scan_returns_flagged_message(
        self, service_with_moderation, mock_moderation_service
    ):
        """Moderation scan should return FlaggedMessage with moderation data."""
        scan_id = uuid4()
        message = BulkScanMessage(
            message_id="123",
            channel_id="456",
            community_server_id="789",
            content="some violent content",
            author_id="user1",
            timestamp=datetime.now(UTC),
        )

        result = await service_with_moderation._run_scanner(
            scan_id, message, "community-platform-id", ScanType.OPENAI_MODERATION
        )

        assert result is not None
        assert result.match_score == 0.95
        assert result.moderation_categories == {"violence": True, "sexual": False}
        assert result.moderation_scores == {"violence": 0.95, "sexual": 0.02}
        assert result.flagged_categories == ["violence"]

    @pytest.mark.asyncio
    async def test_moderation_scan_with_images(
        self, service_with_moderation, mock_moderation_service
    ):
        """Moderation scan should use multimodal when message has attachments."""
        scan_id = uuid4()
        message = BulkScanMessage(
            message_id="123",
            channel_id="456",
            community_server_id="789",
            content="check this image",
            author_id="user1",
            timestamp=datetime.now(UTC),
            attachment_urls=["https://example.com/image.jpg"],
        )

        result = await service_with_moderation._run_scanner(
            scan_id, message, "community-platform-id", ScanType.OPENAI_MODERATION
        )

        assert result is not None
        mock_moderation_service.moderate_multimodal.assert_called_once()

    @pytest.mark.asyncio
    async def test_moderation_scan_unflagged_returns_none(
        self, service_with_moderation, mock_moderation_service
    ):
        """Moderation scan should return None when content is not flagged."""
        from src.bulk_content_scan.openai_moderation_service import ModerationResult

        mock_moderation_service.moderate_text.return_value = ModerationResult(
            flagged=False,
            categories={"violence": False, "sexual": False},
            scores={"violence": 0.01, "sexual": 0.01},
            max_score=0.01,
            flagged_categories=[],
        )

        scan_id = uuid4()
        message = BulkScanMessage(
            message_id="123",
            channel_id="456",
            community_server_id="789",
            content="hello world",
            author_id="user1",
            timestamp=datetime.now(UTC),
        )

        result = await service_with_moderation._run_scanner(
            scan_id, message, "community-platform-id", ScanType.OPENAI_MODERATION
        )

        assert result is None
