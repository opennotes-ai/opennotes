"""Unit tests for PreviouslySeenService."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.fact_checking.previously_seen_service import PreviouslySeenService


class TestPreviouslySeenServiceStoreMethod:
    """Test PreviouslySeenService.store_message_embedding() method."""

    @pytest.mark.asyncio
    async def test_store_returns_none_when_embedding_is_none(self):
        """Test store_message_embedding returns None when embedding is None."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()

        result = await service.store_message_embedding(
            db=mock_db,
            community_server_id=uuid4(),
            original_message_id="123",
            published_note_id=uuid4(),
            embedding=None,  # Missing embedding
        )

        assert result is None
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_creates_record_with_embedding(self):
        """Test store_message_embedding creates record when embedding provided."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is synchronous in SQLAlchemy
        community_server_id = uuid4()
        embedding = [0.1] * 1536

        # Mock the database record after commit
        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.community_server_id = community_server_id
        mock_record.original_message_id = "123"
        mock_record.published_note_id = uuid4()
        mock_record.embedding = embedding
        mock_record.embedding_provider = "openai"
        mock_record.embedding_model = "text-embedding-3-small"
        mock_record.extra_metadata = {}

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = mock_record

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=community_server_id,
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )

            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()
            assert result is not None

    @pytest.mark.asyncio
    async def test_store_includes_provider_and_model(self):
        """Test store_message_embedding includes provider and model metadata."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is synchronous in SQLAlchemy
        embedding = [0.1] * 1536
        community_server_id = uuid4()

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.community_server_id = community_server_id
        mock_record.original_message_id = "123"
        mock_record.published_note_id = uuid4()
        mock_record.embedding = embedding
        mock_record.embedding_provider = "anthropic"
        mock_record.embedding_model = "claude-3-opus"
        mock_record.extra_metadata = {}

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = mock_record

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=community_server_id,
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
                embedding_provider="anthropic",
                embedding_model="claude-3-opus",
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_store_includes_extra_metadata(self):
        """Test store_message_embedding includes extra_metadata."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is synchronous in SQLAlchemy
        embedding = [0.1] * 1536
        metadata = {"channel_name": "general", "author_id": "789"}
        community_server_id = uuid4()

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.community_server_id = community_server_id
        mock_record.original_message_id = "123"
        mock_record.published_note_id = uuid4()
        mock_record.embedding = embedding
        mock_record.embedding_provider = None
        mock_record.embedding_model = None
        mock_record.extra_metadata = metadata

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = mock_record

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=community_server_id,
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
                extra_metadata=metadata,
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_store_handles_none_metadata_gracefully(self):
        """Test store_message_embedding handles None metadata (defaults to empty dict)."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # add() is synchronous in SQLAlchemy
        embedding = [0.1] * 1536
        community_server_id = uuid4()

        mock_record = MagicMock()
        mock_record.id = uuid4()
        mock_record.community_server_id = community_server_id
        mock_record.original_message_id = "123"
        mock_record.published_note_id = uuid4()
        mock_record.embedding = embedding
        mock_record.embedding_provider = None
        mock_record.embedding_model = None
        mock_record.extra_metadata = {}

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = mock_record

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=community_server_id,
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
                extra_metadata=None,  # Should default to {}
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_store_rolls_back_on_exception(self):
        """Test store_message_embedding rolls back transaction on error."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.commit.side_effect = Exception("Database error")
        embedding = [0.1] * 1536

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = MagicMock()

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=uuid4(),
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
            )

            assert result is None
            mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_returns_none_on_exception(self):
        """Test store_message_embedding returns None when exception occurs."""
        service = PreviouslySeenService()
        mock_db = AsyncMock()
        mock_db.add.side_effect = Exception("Add failed")
        embedding = [0.1] * 1536

        with patch("src.fact_checking.previously_seen_service.PreviouslySeenMessage") as mock_model:
            mock_model.return_value = MagicMock()

            result = await service.store_message_embedding(
                db=mock_db,
                community_server_id=uuid4(),
                original_message_id="123",
                published_note_id=uuid4(),
                embedding=embedding,
            )

            assert result is None
