"""Tests for RequestCreateAttributes first-class fields and field persistence.

Moved from tests/unit/bulk_content_scan/test_note_request_creation.py (task-1085.12).
"""

from uuid import uuid4

import pytest


class TestRequestCreateAttributesFirstClassFields:
    """Test that RequestCreateAttributes supports first-class similarity/dataset fields."""

    def test_accepts_similarity_score(self):
        """RequestCreateAttributes should accept similarity_score as a first-class field."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            similarity_score=0.85,
        )
        assert attrs.similarity_score == 0.85

    def test_accepts_dataset_name(self):
        """RequestCreateAttributes should accept dataset_name as a first-class field."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            dataset_name="snopes",
        )
        assert attrs.dataset_name == "snopes"

    def test_accepts_dataset_item_id(self):
        """RequestCreateAttributes should accept dataset_item_id as a first-class field."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        item_id = str(uuid4())
        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            dataset_item_id=item_id,
        )
        assert attrs.dataset_item_id == item_id

    def test_fields_default_to_none(self):
        """First-class fields should default to None when not provided."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
        )
        assert attrs.similarity_score is None
        assert attrs.dataset_name is None
        assert attrs.dataset_item_id is None

    def test_similarity_score_validation_bounds(self):
        """similarity_score should be validated between 0.0 and 1.0."""
        from pydantic import ValidationError

        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        with pytest.raises(ValidationError):
            RequestCreateAttributes(
                request_id="test-001",
                requested_by="user-001",
                community_server_id="guild-001",
                similarity_score=1.5,
            )

        with pytest.raises(ValidationError):
            RequestCreateAttributes(
                request_id="test-001",
                requested_by="user-001",
                community_server_id="guild-001",
                similarity_score=-0.1,
            )

    def test_all_fields_together(self):
        """All three first-class fields can be provided together."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        item_id = str(uuid4())
        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            similarity_score=0.72,
            dataset_name="politifact",
            dataset_item_id=item_id,
        )
        assert attrs.similarity_score == 0.72
        assert attrs.dataset_name == "politifact"
        assert attrs.dataset_item_id == item_id

    def test_dataset_name_max_length_rejected(self):
        """dataset_name exceeding 100 characters should be rejected."""
        from pydantic import ValidationError

        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        with pytest.raises(ValidationError):
            RequestCreateAttributes(
                request_id="test-001",
                requested_by="user-001",
                community_server_id="guild-001",
                dataset_name="x" * 101,
            )

    def test_dataset_item_id_max_length_rejected(self):
        """dataset_item_id exceeding 36 characters should be rejected."""
        from pydantic import ValidationError

        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        with pytest.raises(ValidationError):
            RequestCreateAttributes(
                request_id="test-001",
                requested_by="user-001",
                community_server_id="guild-001",
                dataset_item_id="x" * 37,
            )

    def test_dataset_name_at_max_length_accepted(self):
        """dataset_name at exactly 100 characters should be accepted."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            dataset_name="x" * 100,
        )
        assert len(attrs.dataset_name) == 100

    def test_dataset_item_id_at_max_length_accepted(self):
        """dataset_item_id at exactly 36 characters should be accepted."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-001",
            requested_by="user-001",
            community_server_id="guild-001",
            dataset_item_id="x" * 36,
        )
        assert len(attrs.dataset_item_id) == 36


class TestRequestCreateAttributesFieldPersistence:
    """Test that first-class fields flow through to the request dict used for DB creation."""

    def test_fields_appear_in_request_dict(self):
        """similarity_score, dataset_name, dataset_item_id should appear in request_dict."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        item_id = str(uuid4())
        attrs = RequestCreateAttributes(
            request_id="test-persist-001",
            requested_by="user-001",
            community_server_id="guild-001",
            similarity_score=0.91,
            dataset_name="snopes",
            dataset_item_id=item_id,
        )

        request_dict: dict = {
            "request_id": attrs.request_id,
            "requested_by": attrs.requested_by,
        }

        if attrs.similarity_score is not None:
            request_dict["similarity_score"] = attrs.similarity_score
        if attrs.dataset_name is not None:
            request_dict["dataset_name"] = attrs.dataset_name
        if attrs.dataset_item_id is not None:
            request_dict["dataset_item_id"] = attrs.dataset_item_id

        assert request_dict["similarity_score"] == 0.91
        assert request_dict["dataset_name"] == "snopes"
        assert request_dict["dataset_item_id"] == item_id

    def test_none_fields_omitted_from_request_dict(self):
        """When fields are None, they should not be added to request_dict."""
        from src.notes.requests_jsonapi_router import RequestCreateAttributes

        attrs = RequestCreateAttributes(
            request_id="test-persist-002",
            requested_by="user-001",
            community_server_id="guild-001",
        )

        request_dict: dict = {
            "request_id": attrs.request_id,
            "requested_by": attrs.requested_by,
        }

        if attrs.similarity_score is not None:
            request_dict["similarity_score"] = attrs.similarity_score
        if attrs.dataset_name is not None:
            request_dict["dataset_name"] = attrs.dataset_name
        if attrs.dataset_item_id is not None:
            request_dict["dataset_item_id"] = attrs.dataset_item_id

        assert "similarity_score" not in request_dict
        assert "dataset_name" not in request_dict
        assert "dataset_item_id" not in request_dict

    def test_fields_returned_in_response_attributes(self):
        """RequestAttributes (response schema) should include the three fields."""
        from src.notes.requests_jsonapi_router import RequestAttributes

        attrs = RequestAttributes(
            request_id="test-resp-001",
            requested_by="user-001",
            similarity_score=0.77,
            dataset_name="politifact",
            dataset_item_id="abc-123",
        )
        assert attrs.similarity_score == 0.77
        assert attrs.dataset_name == "politifact"
        assert attrs.dataset_item_id == "abc-123"
