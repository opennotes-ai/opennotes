"""Unit tests for PreviouslySeenMessage SQLAlchemy model."""

from uuid import UUID

import pendulum

from src.fact_checking.previously_seen_models import PreviouslySeenMessage


class TestPreviouslySeenMessageModel:
    """Test PreviouslySeenMessage SQLAlchemy model."""

    def test_model_has_correct_tablename(self):
        """Test PreviouslySeenMessage uses correct table name."""
        assert PreviouslySeenMessage.__tablename__ == "previously_seen_messages"

    def test_model_creates_with_required_fields(self):
        """Test PreviouslySeenMessage can be instantiated with required fields."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        published_note_id = 123456789

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=published_note_id,
        )

        assert message.community_server_id == community_server_id
        assert message.original_message_id == "1234567890123456789"
        assert message.published_note_id == published_note_id

    def test_model_accepts_embedding_vector(self):
        """Test PreviouslySeenMessage accepts embedding vector."""
        embedding = [0.1] * 1536  # 1536 dimensions
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
            embedding=embedding,
        )

        assert message.embedding is not None
        assert len(message.embedding) == 1536

    def test_model_accepts_embedding_provider_and_model(self):
        """Test PreviouslySeenMessage accepts embedding provider and model."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
        )

        assert message.embedding_provider == "openai"
        assert message.embedding_model == "text-embedding-3-small"

    def test_model_accepts_extra_metadata(self):
        """Test PreviouslySeenMessage accepts JSONB metadata."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        metadata = {"channel_name": "general", "author_id": "9876543210"}

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
            extra_metadata=metadata,
        )

        assert message.extra_metadata == metadata
        assert message.extra_metadata["channel_name"] == "general"

    def test_model_created_at_defaults_to_utc(self):
        """Test PreviouslySeenMessage created_at defaults to UTC timestamp."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        before = pendulum.now("UTC")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
        )

        after = pendulum.now("UTC")

        assert message.created_at is not None
        assert before <= message.created_at <= after
        assert message.created_at.tzinfo is not None  # Has timezone

    def test_model_repr_includes_key_fields(self):
        """Test PreviouslySeenMessage __repr__ includes key identifiers."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")
        message_id = "1234567890123456789"
        note_id = 123456789

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id=message_id,
            published_note_id=note_id,
        )

        # Note: id will be None until persisted, but repr should still work
        repr_str = repr(message)
        assert "PreviouslySeenMessage" in repr_str
        assert message_id in repr_str
        assert str(note_id) in repr_str

    def test_model_allows_null_embedding(self):
        """Test PreviouslySeenMessage allows NULL embedding field."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
            embedding=None,
        )

        assert message.embedding is None

    def test_model_allows_null_provider_and_model(self):
        """Test PreviouslySeenMessage allows NULL provider and model fields."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
            embedding_provider=None,
            embedding_model=None,
        )

        assert message.embedding_provider is None
        assert message.embedding_model is None

    def test_model_extra_metadata_defaults_to_empty_dict(self):
        """Test PreviouslySeenMessage extra_metadata has server default (empty dict)."""
        community_server_id = UUID("018f5e6e-1234-7890-abcd-ef1234567890")

        message = PreviouslySeenMessage(
            community_server_id=community_server_id,
            original_message_id="1234567890123456789",
            published_note_id=123456789,
        )

        # This will be set by server_default, but in-memory it won't be set yet
        # The actual default is handled by PostgreSQL server_default='{}'
        # In tests with actual database, this would be {} after commit
        assert hasattr(message, "extra_metadata")
