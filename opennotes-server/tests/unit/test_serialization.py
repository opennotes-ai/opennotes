"""
Test serialization round-trip compatibility for TypeScript type integration.

These tests verify that Pydantic models serialize correctly to JSON in a format
compatible with TypeScript types generated from OpenAPI schema. This ensures
proper cross-language compatibility between Python backend and TypeScript frontend.

Key compatibility requirements:
- UUID fields must serialize as strings (not raw UUID objects)
- Datetime fields must serialize to ISO 8601 format with timezone
- Optional fields must serialize as null (not omitted)
- Enums must serialize as string values
- Computed fields must be included in JSON output

Implementation Notes:
- Tests use model_construct() to bypass validation and directly test serialization
- This simulates the state AFTER ORM → Pydantic conversion (which includes field_validators)
- In production: ORM integer → field_validator → Pydantic string → JSON serializer → string output
- In tests: We skip the validator step and provide data in post-validation state
"""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.notes.schemas import (
    NoteResponse,
    RatingResponse,
    RequestInfo,
    RequestResponse,
)


class TestRequestResponseSerialization:
    """Test RequestResponse serialization for TypeScript compatibility."""

    @pytest.mark.asyncio
    async def test_request_response_platform_message_id_serializes_as_string(self):
        """
        Test that RequestResponse.platform_message_id serializes as string.

        TypeScript expects: platform_message_id?: string (platform-specific message ID)

        Note: platform_message_id is optional and stores platform-specific message IDs as strings.
        """
        # Arrange: Create RequestResponse with platform_message_id
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "requested_by": "user_123",
            "requested_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "status": "PENDING",
            "note_id": None,
            "platform_message_id": "1234567890123456789",  # Platform message ID
            "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        class MockRequest:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockRequest(**request_data)

        # Act: Convert to Pydantic schema and serialize to JSON
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json")

        # Assert: platform_message_id is serialized as string
        assert isinstance(json_output["platform_message_id"], str)
        assert json_output["platform_message_id"] == "1234567890123456789"

        # Verify JSON roundtrip preserves string type
        json_str = json.dumps(json_output)
        parsed = json.loads(json_str)
        assert isinstance(parsed["platform_message_id"], str)
        assert parsed["platform_message_id"] == "1234567890123456789"

    @pytest.mark.asyncio
    async def test_request_response_note_id_serializes_as_uuid_when_present(self):
        """
        Test that RequestResponse.note_id serializes as UUID string when not None.

        TypeScript expects: note_id?: string | null (per generated-types.ts line 3313)
        """
        # Arrange: Create RequestResponse with note_id (UUID FK to Note)
        note_uuid = uuid4()
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "platform_message_id": "1234567890123456789",  # String (post-validator state)
            "requested_by": "user_123",
            "requested_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "status": "COMPLETED",
            "note_id": note_uuid,  # UUID FK to Note
            "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        # Act: Create schema using model_construct and serialize to JSON
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json")

        # Assert: note_id is serialized as UUID string
        assert isinstance(json_output["note_id"], str)
        assert json_output["note_id"] == str(note_uuid)

    @pytest.mark.asyncio
    async def test_request_response_note_id_serializes_as_null_when_none(self):
        """
        Test that RequestResponse.note_id serializes as null when None.

        TypeScript expects: note_id?: string | null
        """
        # Arrange: Create RequestResponse with note_id=None
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "platform_message_id": "1234567890123456789",  # String (post-validator state)
            "requested_by": "user_123",
            "requested_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "status": "PENDING",
            "note_id": None,
            "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        # Act: Create schema and serialize to JSON
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json")

        # Assert: note_id is null (not omitted from output)
        assert "note_id" in json_output
        assert json_output["note_id"] is None

    @pytest.mark.asyncio
    async def test_request_response_datetime_serializes_to_iso8601_with_timezone(self):
        """
        Test that RequestResponse.requested_at serializes to ISO 8601 format with timezone.

        TypeScript expects: requested_at: string (per generated-types.ts line 3307)
        JavaScript Date constructor requires ISO 8601 format with timezone.
        """
        # Arrange: Create RequestResponse with timezone-aware datetime
        requested_at = datetime(2025, 1, 15, 14, 30, 45, 123456, tzinfo=UTC)
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "platform_message_id": "1234567890123456789",  # String (post-validator state)
            "requested_by": "user_123",
            "requested_at": requested_at,
            "status": "PENDING",
            "note_id": None,
            "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        # Act: Create schema and serialize to JSON
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json")

        # Assert: requested_at is ISO 8601 string with timezone
        assert isinstance(json_output["requested_at"], str)
        # Should be in format: 2025-01-15T14:30:45.123456+00:00
        assert json_output["requested_at"].startswith("2025-01-15T14:30:45")
        assert "+00:00" in json_output["requested_at"] or "Z" in json_output["requested_at"]

        # Verify JavaScript can parse this format (simulated with Python datetime.fromisoformat)
        parsed_dt = datetime.fromisoformat(json_output["requested_at"])
        assert parsed_dt.tzinfo is not None  # Must have timezone


class TestNoteResponseSerialization:
    """Test NoteResponse serialization for TypeScript compatibility."""

    @pytest.mark.asyncio
    async def test_note_response_id_serializes_as_uuid_string(self):
        """
        Test that NoteResponse id serializes as UUID string.

        TypeScript expects id: string (UUID)
        """
        # Arrange: Create NoteResponse
        note_id = uuid4()
        note_data = {
            "id": note_id,
            "community_server_id": uuid4(),
            "author_id": "author_123",
            "summary": "Test note",
            "classification": "NOT_MISLEADING",
            "helpfulness_score": 85,
            "status": "CURRENTLY_RATED_HELPFUL",
            "created_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "updated_at": None,
            "ratings": [],
        }

        class MockNote:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockNote(**note_data)

        # Act: Serialize to JSON
        schema = NoteResponse.model_construct(**note_data)
        json_output = schema.model_dump(mode="json")

        # Assert: id is string (UUID compatibility)
        assert isinstance(json_output["id"], str)
        assert json_output["id"] == str(note_id)

    @pytest.mark.asyncio
    async def test_note_response_computed_field_included_in_json(self):
        """
        Test that NoteResponse.ratings_count computed field is included in JSON output.

        TypeScript expects: readonly ratings_count: number (per generated-types.ts line 2860)
        """
        # Arrange: Create NoteResponse with ratings
        note_id = uuid4()
        rating1_data = {
            "id": uuid4(),
            "note_id": note_id,  # UUID FK to Note
            "rater_id": "rater_1",
            "helpfulness_level": "HELPFUL",
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        rating2_data = {
            "id": uuid4(),
            "note_id": note_id,  # UUID FK to Note
            "rater_id": "rater_2",
            "helpfulness_level": "SOMEWHAT_HELPFUL",
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
            "community_server_id": uuid4(),
            "author_id": "author_123",
            "summary": "Note with ratings",
            "classification": "NOT_MISLEADING",
            "helpfulness_score": 75,
            "status": "CURRENTLY_RATED_HELPFUL",
            "created_at": datetime.now(UTC),
            "updated_at": None,
            "ratings": ratings,
        }

        class MockNote:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockNote(**note_data)

        # Act: Serialize to JSON
        schema = NoteResponse.model_construct(**note_data)
        json_output = schema.model_dump(mode="json")

        # Assert: ratings_count is included and correct  # noqa: ERA001
        assert "ratings_count" in json_output
        assert json_output["ratings_count"] == 2
        assert isinstance(json_output["ratings_count"], int)

    @pytest.mark.asyncio
    async def test_note_response_enum_serializes_as_string(self):
        """
        Test that NoteResponse enums (classification, status) serialize as strings.

        TypeScript expects:
        - classification: NoteClassification (string enum)
        - status: NoteStatus (string enum)
        """
        # Arrange: Create NoteResponse with enum fields
        note_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "author_id": "author_123",
            "summary": "Test note",
            "classification": "MISINFORMED_OR_POTENTIALLY_MISLEADING",
            "helpfulness_score": 30,
            "status": "NEEDS_MORE_RATINGS",
            "created_at": datetime.now(UTC),
            "updated_at": None,
            "ratings": [],
        }

        class MockNote:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockNote(**note_data)

        # Act: Serialize to JSON
        schema = NoteResponse.model_construct(**note_data)
        json_output = schema.model_dump(mode="json")

        # Assert: Enums are strings
        assert isinstance(json_output["classification"], str)
        assert json_output["classification"] == "MISINFORMED_OR_POTENTIALLY_MISLEADING"
        assert isinstance(json_output["status"], str)
        assert json_output["status"] == "NEEDS_MORE_RATINGS"


class TestRatingResponseSerialization:
    """Test RatingResponse serialization for TypeScript compatibility."""

    @pytest.mark.asyncio
    async def test_rating_response_note_id_serializes_as_uuid_string(self):
        """
        Test that RatingResponse.note_id serializes as UUID string.
        """
        # Arrange: Create RatingResponse with UUID note_id (FK to Note)
        note_uuid = uuid4()
        rating_data = {
            "id": uuid4(),
            "note_id": note_uuid,  # UUID FK to Note
            "rater_id": "rater_123",
            "helpfulness_level": "HELPFUL",
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }

        class MockRating:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockRating(**rating_data)

        # Act: Serialize to JSON
        schema = RatingResponse.model_construct(**rating_data)
        json_output = schema.model_dump(mode="json")

        # Assert: note_id is UUID string
        assert isinstance(json_output["note_id"], str)
        assert json_output["note_id"] == str(note_uuid)


class TestOptionalFieldSerialization:
    """Test that optional fields serialize correctly (null vs undefined)."""

    @pytest.mark.asyncio
    async def test_optional_fields_serialize_as_null_not_omitted(self):
        """
        Test that optional fields serialize as null (not omitted from JSON).

        TypeScript distinguishes between:
        - field?: string | null  (field present with null value)
        - field?: string         (field omitted entirely)

        Our OpenAPI schema uses the former, so we must include null fields.
        """
        # Arrange: Create RequestResponse with optional fields set to None
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "requested_by": "user_123",
            "requested_at": datetime.now(UTC),
            "status": "PENDING",
            "note_id": None,
            "content": None,
            "platform_message_id": None,
            "request_metadata": None,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }

        class MockRequest:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockRequest(**request_data)

        # Act: Serialize to JSON
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json")

        # Assert: Optional fields are present with null values
        assert "note_id" in json_output
        assert json_output["note_id"] is None
        assert "content" in json_output
        assert json_output["content"] is None
        assert "platform_message_id" in json_output
        assert json_output["platform_message_id"] is None
        assert "updated_at" in json_output
        assert json_output["updated_at"] is None

        # Verify JSON serialization preserves null (not omits fields)
        json_str = json.dumps(json_output)
        assert '"note_id":null' in json_str or '"note_id": null' in json_str


class TestModelDumpJsonMode:
    """Test model_dump(mode='json') for JavaScript-safe serialization."""

    @pytest.mark.asyncio
    async def test_model_dump_json_mode_serializes_uuids_as_strings(self):
        """
        Test that model_dump(mode='json') serializes UUID fields as strings.

        This is the critical test ensuring our JSON output matches TypeScript expectations.
        """
        # Arrange: Create NoteResponse with UUIDs
        note_id = uuid4()
        community_id = uuid4()
        note_data = {
            "id": note_id,
            "community_server_id": community_id,
            "author_id": "author_123",
            "summary": "Test note",
            "classification": "NOT_MISLEADING",
            "helpfulness_score": 85,
            "status": "CURRENTLY_RATED_HELPFUL",
            "created_at": datetime.now(UTC),
            "updated_at": None,
            "ratings": [],
        }

        class MockNote:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockNote(**note_data)

        # Act: Serialize using model_dump(mode='json')
        schema = NoteResponse.model_construct(**note_data)
        json_output = schema.model_dump(mode="json")

        # Assert: UUIDs are strings (JavaScript-safe)
        assert isinstance(json_output["id"], str)
        assert isinstance(json_output["community_server_id"], str)

        # Verify JSON roundtrip doesn't lose precision
        json_str = json.dumps(json_output)
        parsed = json.loads(json_str)
        assert parsed["id"] == str(note_id)
        assert parsed["community_server_id"] == str(community_id)

    @pytest.mark.asyncio
    async def test_model_dump_python_mode_preserves_types(self):
        """
        Test that model_dump(mode='python') preserves Python types correctly.

        This verifies the distinction between 'json' and 'python' serialization modes.
        """
        # Arrange: Create RequestResponse
        request_data = {
            "id": uuid4(),
            "community_server_id": uuid4(),
            "request_id": "req_12345",
            "requested_by": "user_123",
            "requested_at": datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            "status": "PENDING",
            "note_id": None,
            "platform_message_id": "msg_123",
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }

        class MockRequest:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockRequest(**request_data)

        # Act: Serialize using model_dump(mode='python')
        schema = RequestResponse.model_construct(**request_data)
        python_output = schema.model_dump(mode="python")

        assert isinstance(python_output["platform_message_id"], str)
        assert python_output["request_id"] == "req_12345"


class TestPydanticToTypeScriptCompatibility:
    """Test end-to-end Pydantic → JSON → TypeScript compatibility."""

    @pytest.mark.asyncio
    async def test_full_request_response_json_matches_typescript_expectations(self):
        """
        Test complete RequestResponse JSON output matches TypeScript type definition.

        Verifies all field types and formats are TypeScript-compatible.
        """
        # Arrange: Create realistic RequestResponse
        community_server_id = uuid4()
        note_uuid = uuid4()
        request_data = {
            "id": uuid4(),
            "request_id": "req_abc123",
            "requested_by": "discord_user_123",
            "community_server_id": community_server_id,
            "requested_at": datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            "status": "COMPLETED",
            "note_id": note_uuid,  # UUID FK to Note
            "content": "Original message content",
            "platform_message_id": "1234567890123456789",
            "request_metadata": {"dataset_item_id": "123", "similarity_score": 0.95},
            "created_at": datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            "updated_at": datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC),
        }

        class MockRequest:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockRequest(**request_data)

        # Act: Serialize to JSON (use by_alias=True to apply serialization_alias)
        schema = RequestResponse.model_construct(**request_data)
        json_output = schema.model_dump(mode="json", by_alias=True)

        # Assert: All fields match TypeScript expectations
        assert isinstance(json_output["id"], str)  # UUID as string
        assert json_output["request_id"] == "req_abc123"  # string
        assert json_output["requested_by"] == "discord_user_123"  # string
        assert isinstance(json_output["community_server_id"], str)  # UUID as string
        assert json_output["requested_at"].startswith("2025-01-15T10:30:00")  # ISO 8601
        assert json_output["status"] == "COMPLETED"  # enum string
        assert json_output["note_id"] == str(note_uuid)  # UUID as string
        assert json_output["content"] == "Original message content"  # string
        assert json_output["platform_message_id"] == "1234567890123456789"  # string
        # Note: request_metadata has serialization_alias="metadata" so it appears as "metadata" in JSON
        assert json_output["metadata"]["dataset_item_id"] == "123"  # dict
        assert json_output["metadata"]["similarity_score"] == 0.95

        # Verify JSON is valid and parseable
        json_str = json.dumps(json_output)
        parsed = json.loads(json_str)
        assert parsed["platform_message_id"] == "1234567890123456789"  # No precision loss

    @pytest.mark.asyncio
    async def test_full_note_response_json_matches_typescript_expectations(self):
        """
        Test complete NoteResponse JSON output matches TypeScript type definition.

        Includes nested ratings and computed fields.
        """
        # Arrange: Create realistic NoteResponse with ratings
        note_id = uuid4()
        rating1_data = {
            "id": uuid4(),
            "note_id": note_id,  # UUID FK to Note
            "rater_id": "rater_1",
            "helpfulness_level": "HELPFUL",
            "created_at": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        rating2_data = {
            "id": uuid4(),
            "note_id": note_id,  # UUID FK to Note
            "rater_id": "rater_2",
            "helpfulness_level": "SOMEWHAT_HELPFUL",
            "created_at": datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC),
            "updated_at": None,
        }

        class MockRating:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        ratings = [MockRating(**rating1_data), MockRating(**rating2_data)]

        request_info = RequestInfo(
            request_id="req_123",
            content="Original message",
            requested_by="user_123",
            requested_at=datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC),
        )

        note_data = {
            "id": note_id,
            "community_server_id": uuid4(),
            "author_id": "author_123",
            "channel_id": "channel_789",
            "request_id": "req_123",
            "summary": "This is a test community note",
            "classification": "NOT_MISLEADING",
            "helpfulness_score": 85,
            "status": "CURRENTLY_RATED_HELPFUL",
            "created_at": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            "updated_at": None,
            "ratings": ratings,
            "request": request_info,
        }

        class MockNote:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        MockNote(**note_data)

        # Act: Serialize to JSON
        schema = NoteResponse.model_construct(**note_data)
        json_output = schema.model_dump(mode="json")

        # Assert: All fields match TypeScript expectations
        assert isinstance(json_output["id"], str)  # UUID as string
        assert json_output["author_id"] == "author_123"  # string
        assert json_output["channel_id"] == "channel_789"  # string
        assert json_output["request_id"] == "req_123"  # string
        assert json_output["summary"] == "This is a test community note"  # string
        assert json_output["classification"] == "NOT_MISLEADING"  # enum string
        assert json_output["helpfulness_score"] == 85  # number
        assert json_output["status"] == "CURRENTLY_RATED_HELPFUL"  # enum string
        assert isinstance(json_output["created_at"], str)  # ISO 8601 datetime
        assert json_output["updated_at"] is None  # null
        assert len(json_output["ratings"]) == 2  # array of RatingResponse
        assert json_output["ratings"][0]["note_id"] == str(note_id)  # UUID as string
        assert json_output["ratings"][0]["helpfulness_level"] == "HELPFUL"  # enum string
        assert json_output["ratings_count"] == 2  # computed field
        assert json_output["request"]["request_id"] == "req_123"  # nested object

        # Verify JSON is valid
        json_str = json.dumps(json_output)
        parsed = json.loads(json_str)
        assert parsed["id"] == str(note_id)  # UUIDs preserved correctly
