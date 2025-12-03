"""
Test SQLAlchemy model to Pydantic schema compatibility.

These tests verify that SQLAlchemy models can be converted to Pydantic schemas
using model_validate() with from_attributes=True configuration.

Note: Additional integration test coverage for model/schema compatibility is
provided in test_notes_router.py, which creates and retrieves notes via the API
(internally using model_validate for all conversions).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.notes.schemas import (
    NoteInDB,
    NoteResponse,
    RatingResponse,
    RequestResponse,
)


@pytest.mark.asyncio
async def test_note_model_basic_conversion():
    """Test that Note models can be converted to Pydantic schemas using model_validate."""
    # This is a unit test demonstrating the conversion pattern
    # No database interaction required
    note_id = uuid4()
    community_server_id = uuid4()
    note_data = {
        "id": note_id,
        "author_participant_id": "author_123",
        "community_server_id": community_server_id,
        "summary": "Test community note",
        "classification": "NOT_MISLEADING",
        "helpfulness_score": 75,
        "status": "CURRENTLY_RATED_HELPFUL",
        "created_at": datetime.now(UTC),
        "updated_at": None,
        "ratings": [],
    }

    # Create a mock note object
    class MockNote:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    note = MockNote(**note_data)

    # Convert to Pydantic schema using model_validate
    schema = NoteInDB.model_validate(note)

    # Verify conversion worked
    assert schema.id == note_id
    assert schema.author_participant_id == note_data["author_participant_id"]
    assert schema.summary == note_data["summary"]
    assert schema.community_server_id == community_server_id
    # With use_enum_values=True, enums are returned as strings
    assert schema.classification == "NOT_MISLEADING"
    assert schema.status == "CURRENTLY_RATED_HELPFUL"


@pytest.mark.asyncio
async def test_rating_model_basic_conversion():
    """Test that Rating models can be converted to Pydantic schemas."""
    rating_id = uuid4()
    note_id = uuid4()
    rating_data = {
        "id": rating_id,
        "note_id": note_id,
        "rater_participant_id": "rater_123",
        "helpfulness_level": "HELPFUL",
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }

    class MockRating:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    rating = MockRating(**rating_data)

    # Convert to Pydantic schema
    schema = RatingResponse.model_validate(rating)

    # Verify conversion
    assert schema.id == rating_id
    assert schema.note_id == note_id
    assert schema.rater_participant_id == rating_data["rater_participant_id"]
    assert schema.helpfulness_level == "HELPFUL"


@pytest.mark.asyncio
async def test_request_model_basic_conversion():
    """Test that Request models can be converted to Pydantic schemas."""
    request_id_uuid = uuid4()
    community_server_id = uuid4()
    request_data = {
        "id": request_id_uuid,
        "request_id": "req_12345",
        "community_server_id": community_server_id,
        "requested_by": "requester_123",
        "requested_at": datetime.now(UTC),
        "status": "PENDING",
        "note_id": None,
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }

    class MockRequest:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    request = MockRequest(**request_data)

    # Convert to Pydantic schema
    schema = RequestResponse.model_validate(request)

    # Verify conversion
    assert schema.id == request_id_uuid
    assert schema.request_id == request_data["request_id"]
    assert schema.community_server_id == community_server_id
    assert schema.requested_by == request_data["requested_by"]
    assert schema.status == "PENDING"
    assert schema.note_id is None


@pytest.mark.asyncio
async def test_note_with_ratings_conversion():
    """Test that Note with nested ratings can be converted to NoteResponse."""
    note_id = uuid4()
    community_server_id = uuid4()
    rating1_id = uuid4()
    rating2_id = uuid4()

    rating1_data = {
        "id": rating1_id,
        "note_id": note_id,
        "rater_participant_id": "rater_1",
        "helpfulness_level": "HELPFUL",
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }

    rating2_data = {
        "id": rating2_id,
        "note_id": note_id,
        "rater_participant_id": "rater_2",
        "helpfulness_level": "NOT_HELPFUL",
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }

    class MockRating:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    ratings = [MockRating(**rating1_data), MockRating(**rating2_data)]

    note_data = {
        "id": note_id,
        "author_participant_id": "author_rel_test",
        "community_server_id": community_server_id,
        "summary": "Note with ratings",
        "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
        "helpfulness_score": 30,
        "status": "NEEDS_MORE_RATINGS",
        "created_at": datetime.now(UTC),
        "updated_at": None,
        "ratings": ratings,
    }

    class MockNote:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    note = MockNote(**note_data)

    # Convert to NoteResponse with nested ratings
    schema = NoteResponse.model_validate(note)

    # Verify note fields
    assert schema.id == note_id
    assert schema.classification == "MISINFORMED_OR_POTENTIALLY_MISLEADING"

    # Verify ratings relationship
    assert len(schema.ratings) == 2
    assert all(isinstance(r, RatingResponse) for r in schema.ratings)

    # Verify computed field
    assert schema.ratings_count == 2


@pytest.mark.asyncio
async def test_enum_values_use_string_representation():
    """Test that enum values are converted to strings due to use_enum_values=True."""
    note_id = uuid4()
    community_server_id = uuid4()
    note_data = {
        "id": note_id,
        "author_participant_id": "author_enum",
        "community_server_id": community_server_id,
        "summary": "Testing enum conversion",
        "classification": "NOT_MISLEADING",
        "helpfulness_score": 0,
        "status": "NEEDS_MORE_RATINGS",
        "created_at": datetime.now(UTC),
        "updated_at": None,
        "ratings": [],
    }

    class MockNote:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    note = MockNote(**note_data)
    schema = NoteInDB.model_validate(note)

    # With use_enum_values=True in SQLAlchemySchema base class,
    # enum values are returned as strings, not enum instances
    assert isinstance(schema.classification, str)
    assert isinstance(schema.status, str)
    assert schema.classification == "NOT_MISLEADING"
    assert schema.status == "NEEDS_MORE_RATINGS"
