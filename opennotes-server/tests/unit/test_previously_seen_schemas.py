"""Unit tests for PreviouslySeenMessage Pydantic schemas."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from src.fact_checking.previously_seen_schemas import (
    PreviouslySeenMessageBase,
    PreviouslySeenMessageCreate,
    PreviouslySeenMessageMatch,
    PreviouslySeenMessageResponse,
    PreviouslySeenMessageUpdate,
    PreviouslySeenSearchResponse,
)


class TestPreviouslySeenMessageBaseSchema:
    """Test PreviouslySeenMessageBase schema validation."""

    def test_base_schema_validates_with_required_fields(self):
        """Test base schema validates with all required fields."""
        community_server_id = uuid4()
        published_note_id = uuid4()
        data = {
            "community_server_id": community_server_id,
            "original_message_id": "1234567890123456789",
            "published_note_id": published_note_id,
        }

        schema = PreviouslySeenMessageBase(**data)

        assert schema.community_server_id == community_server_id
        assert schema.original_message_id == "1234567890123456789"
        assert schema.published_note_id == published_note_id

    def test_base_schema_accepts_optional_embedding(self):
        """Test base schema accepts optional embedding field."""
        embedding = [0.1] * 1536
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "embedding": embedding,
        }

        schema = PreviouslySeenMessageBase(**data)

        assert schema.embedding is not None
        assert len(schema.embedding) == 1536

    def test_base_schema_accepts_provider_and_model(self):
        """Test base schema accepts embedding provider and model."""
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
        }

        schema = PreviouslySeenMessageBase(**data)

        assert schema.embedding_provider == "openai"
        assert schema.embedding_model == "text-embedding-3-small"

    def test_base_schema_accepts_extra_metadata(self):
        """Test base schema accepts extra_metadata dict."""
        metadata = {"channel_name": "general", "author_id": "9876543210"}
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "extra_metadata": metadata,
        }

        schema = PreviouslySeenMessageBase(**data)

        assert schema.extra_metadata == metadata

    def test_base_schema_extra_metadata_defaults_to_empty_dict(self):
        """Test base schema extra_metadata defaults to empty dict."""
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
        }

        schema = PreviouslySeenMessageBase(**data)

        assert schema.extra_metadata == {}

    def test_base_schema_rejects_invalid_message_id_length(self):
        """Test base schema rejects message_id exceeding max_length."""
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "x" * 65,  # max_length=64
            "published_note_id": uuid4(),
        }

        with pytest.raises(ValidationError) as exc_info:
            PreviouslySeenMessageBase(**data)

        errors = exc_info.value.errors()
        assert any(
            error["loc"] == ("original_message_id",) and "string_too_long" in error["type"]
            for error in errors
        )

    def test_base_schema_rejects_missing_required_fields(self):
        """Test base schema rejects missing required fields."""
        data = {
            "community_server_id": uuid4(),
            # Missing original_message_id and published_note_id
        }

        with pytest.raises(ValidationError) as exc_info:
            PreviouslySeenMessageBase(**data)

        errors = exc_info.value.errors()
        assert len(errors) >= 2  # At least 2 missing fields


class TestPreviouslySeenMessageCreateSchema:
    """Test PreviouslySeenMessageCreate schema (inherits from Base)."""

    def test_create_schema_validates_with_all_fields(self):
        """Test create schema validates with complete data."""
        embedding = [0.1] * 1536
        metadata = {"test": "data"}
        data = {
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "embedding": embedding,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "extra_metadata": metadata,
        }

        schema = PreviouslySeenMessageCreate(**data)

        assert schema.embedding == embedding
        assert schema.embedding_provider == "openai"
        assert schema.extra_metadata == metadata


class TestPreviouslySeenMessageUpdateSchema:
    """Test PreviouslySeenMessageUpdate schema."""

    def test_update_schema_allows_metadata_update(self):
        """Test update schema allows metadata updates."""
        metadata = {"updated": "value"}
        schema = PreviouslySeenMessageUpdate(extra_metadata=metadata)

        assert schema.extra_metadata == metadata

    def test_update_schema_allows_none_metadata(self):
        """Test update schema allows None metadata (no update)."""
        schema = PreviouslySeenMessageUpdate(extra_metadata=None)

        assert schema.extra_metadata is None

    def test_update_schema_can_be_empty(self):
        """Test update schema can be instantiated without fields (partial update)."""
        schema = PreviouslySeenMessageUpdate()

        assert schema.extra_metadata is None


class TestPreviouslySeenMessageResponseSchema:
    """Test PreviouslySeenMessageResponse schema."""

    def test_response_schema_includes_id_and_timestamps(self):
        """Test response schema includes id and created_at."""
        data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
        }

        schema = PreviouslySeenMessageResponse(**data)

        assert isinstance(schema.id, UUID)
        assert isinstance(schema.created_at, datetime)

    def test_response_schema_validates_with_all_fields(self):
        """Test response schema validates with complete data."""
        embedding = [0.1] * 1536
        data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "embedding": embedding,
            "embedding_provider": "openai",
            "embedding_model": "text-embedding-3-small",
            "extra_metadata": {"test": "data"},
            "created_at": datetime.now(UTC),
        }

        schema = PreviouslySeenMessageResponse(**data)

        assert schema.embedding == embedding
        assert schema.embedding_provider == "openai"


class TestPreviouslySeenMessageMatchSchema:
    """Test PreviouslySeenMessageMatch schema (with similarity_score)."""

    def test_match_schema_requires_similarity_score(self):
        """Test match schema requires similarity_score field."""
        data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
            "similarity_score": 0.85,
        }

        schema = PreviouslySeenMessageMatch(**data)

        assert schema.similarity_score == 0.85

    def test_match_schema_validates_similarity_score_range(self):
        """Test match schema validates similarity_score is in 0.0-1.0 range."""
        data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
            "similarity_score": 1.5,  # Invalid: > 1.0
        }

        with pytest.raises(ValidationError) as exc_info:
            PreviouslySeenMessageMatch(**data)

        errors = exc_info.value.errors()
        assert any(
            error["loc"] == ("similarity_score",) and "less_than_equal" in error["type"]
            for error in errors
        )

    def test_match_schema_rejects_negative_similarity(self):
        """Test match schema rejects negative similarity scores."""
        data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
            "similarity_score": -0.1,  # Invalid: < 0.0
        }

        with pytest.raises(ValidationError) as exc_info:
            PreviouslySeenMessageMatch(**data)

        errors = exc_info.value.errors()
        assert any(
            error["loc"] == ("similarity_score",) and "greater_than_equal" in error["type"]
            for error in errors
        )

    def test_match_schema_accepts_boundary_scores(self):
        """Test match schema accepts boundary values 0.0 and 1.0."""
        # Test 0.0
        data_zero = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
            "similarity_score": 0.0,
        }
        schema_zero = PreviouslySeenMessageMatch(**data_zero)
        assert schema_zero.similarity_score == 0.0

        # Test 1.0
        data_one = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "original_message_id": "1234567890123456789",
            "published_note_id": uuid4(),
            "created_at": datetime.now(UTC),
            "similarity_score": 1.0,
        }
        schema_one = PreviouslySeenMessageMatch(**data_one)
        assert schema_one.similarity_score == 1.0


class TestPreviouslySeenSearchResponseSchema:
    """Test PreviouslySeenSearchResponse schema."""

    def test_search_response_validates_with_required_fields(self):
        """Test search response schema validates with required fields."""
        matches = [
            {
                "id": uuid4(),
                "community_server_id": uuid4(),
                "original_message_id": "1234567890123456789",
                "published_note_id": uuid4(),
                "created_at": datetime.now(UTC),
                "similarity_score": 0.9,
            }
        ]
        data = {
            "matches": matches,
            "query_text": "test message",
            "similarity_threshold": 0.75,
            "total_matches": 1,
        }

        schema = PreviouslySeenSearchResponse(**data)

        assert len(schema.matches) == 1
        assert schema.query_text == "test message"
        assert schema.similarity_threshold == 0.75
        assert schema.total_matches == 1

    def test_search_response_accepts_empty_matches(self):
        """Test search response schema accepts empty matches list."""
        data = {
            "matches": [],
            "query_text": "no matches",
            "similarity_threshold": 0.9,
            "total_matches": 0,
        }

        schema = PreviouslySeenSearchResponse(**data)

        assert schema.matches == []
        assert schema.total_matches == 0

    def test_search_response_validates_match_items(self):
        """Test search response schema validates each match item."""
        matches = [
            {
                "id": uuid4(),
                "community_server_id": uuid4(),
                "original_message_id": "msg1",
                "published_note_id": uuid4(),
                "created_at": datetime.now(UTC),
                "similarity_score": 0.95,
            },
            {
                "id": uuid4(),
                "community_server_id": uuid4(),
                "original_message_id": "msg2",
                "published_note_id": uuid4(),
                "created_at": datetime.now(UTC),
                "similarity_score": 0.85,
            },
        ]
        data = {
            "matches": matches,
            "query_text": "test",
            "similarity_threshold": 0.8,
            "total_matches": 2,
        }

        schema = PreviouslySeenSearchResponse(**data)

        assert len(schema.matches) == 2
        assert schema.matches[0].similarity_score == 0.95
        assert schema.matches[1].similarity_score == 0.85
