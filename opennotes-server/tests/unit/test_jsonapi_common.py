"""Unit tests for JSON:API common infrastructure.

This module tests the reusable JSON:API components in src/common/jsonapi.py:
- Base response schemas (JSONAPIResource, JSONAPIListResponse, etc.)
- Pagination link generation
- Error response formatting
- Model-to-resource conversion
"""

from datetime import UTC, datetime
from uuid import uuid4


class TestJSONAPIResourceConversion:
    """Tests for converting models to JSON:API resource objects."""

    def test_model_to_resource_basic(self):
        """Test basic model to JSON:API resource conversion."""
        from src.common.jsonapi import model_to_resource

        class MockModel:
            id = "test-123"
            name = "Test Name"
            status = "active"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
        )

        assert resource.type == "tests"
        assert resource.id == "test-123"
        assert resource.attributes["name"] == "Test Name"
        assert resource.attributes["status"] == "active"

    def test_model_to_resource_with_uuid_id(self):
        """Test conversion with UUID id field."""
        from src.common.jsonapi import model_to_resource

        test_uuid = uuid4()

        class MockModel:
            id = test_uuid
            title = "Test Title"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="items",
        )

        assert resource.id == str(test_uuid)
        assert resource.attributes["title"] == "Test Title"

    def test_model_to_resource_excludes_id_from_attributes(self):
        """Test that id field is excluded from attributes."""
        from src.common.jsonapi import model_to_resource

        class MockModel:
            id = "test-id"
            name = "Test"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
        )

        assert "id" not in resource.attributes

    def test_model_to_resource_with_exclude_fields(self):
        """Test excluding specific fields from attributes."""
        from src.common.jsonapi import model_to_resource

        class MockModel:
            id = "test-id"
            public_field = "public"
            private_field = "secret"
            internal_state = "internal"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
            exclude_fields={"private_field", "internal_state"},
        )

        assert resource.attributes["public_field"] == "public"
        assert "private_field" not in resource.attributes
        assert "internal_state" not in resource.attributes

    def test_model_to_resource_with_custom_id_field(self):
        """Test using a custom field as the id."""
        from src.common.jsonapi import model_to_resource

        class MockModel:
            uuid = "custom-uuid-123"
            name = "Test"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
            id_field="uuid",
        )

        assert resource.id == "custom-uuid-123"
        assert "uuid" not in resource.attributes

    def test_model_to_resource_with_datetime(self):
        """Test that datetime fields are properly converted."""
        from src.common.jsonapi import model_to_resource

        now = datetime.now(UTC)

        class MockModel:
            id = "test-id"
            created_at = now

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
        )

        assert resource.attributes["created_at"] == now

    def test_model_to_resource_with_none_values(self):
        """Test that None values are preserved in attributes."""
        from src.common.jsonapi import model_to_resource

        class MockModel:
            id = "test-id"
            optional_field = None
            required_field = "present"

        resource = model_to_resource(
            model=MockModel(),
            resource_type="tests",
        )

        assert resource.attributes["optional_field"] is None
        assert resource.attributes["required_field"] == "present"


class TestPaginationLinks:
    """Tests for JSON:API pagination link generation."""

    def test_pagination_links_first_page(self):
        """Test pagination links for the first page."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=1,
            size=20,
            total=100,
        )

        assert links.self_ is not None
        assert "page[number]=1" in links.self_
        assert "page[size]=20" in links.self_

        assert links.first is not None
        assert "page[number]=1" in links.first

        assert links.last is not None
        assert "page[number]=5" in links.last

        assert links.prev is None

        assert links.next_ is not None
        assert "page[number]=2" in links.next_

    def test_pagination_links_middle_page(self):
        """Test pagination links for a middle page."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=3,
            size=20,
            total=100,
        )

        assert links.self_ is not None
        assert "page[number]=3" in links.self_

        assert links.first is not None
        assert "page[number]=1" in links.first

        assert links.last is not None
        assert "page[number]=5" in links.last

        assert links.prev is not None
        assert "page[number]=2" in links.prev

        assert links.next_ is not None
        assert "page[number]=4" in links.next_

    def test_pagination_links_last_page(self):
        """Test pagination links for the last page."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=5,
            size=20,
            total=100,
        )

        assert links.self_ is not None
        assert "page[number]=5" in links.self_

        assert links.prev is not None
        assert "page[number]=4" in links.prev

        assert links.next_ is None

    def test_pagination_links_single_page(self):
        """Test pagination links when all results fit on one page."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=1,
            size=20,
            total=15,
        )

        assert links.self_ is not None
        assert links.first is not None
        assert links.last is not None
        assert links.prev is None
        assert links.next_ is None

    def test_pagination_links_empty_results(self):
        """Test pagination links with no results."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=1,
            size=20,
            total=0,
        )

        assert links.self_ is not None
        assert links.first is None
        assert links.last is None
        assert links.prev is None
        assert links.next_ is None

    def test_pagination_links_preserves_query_params(self):
        """Test that pagination links preserve existing query parameters."""
        from src.common.jsonapi import create_pagination_links

        links = create_pagination_links(
            base_url="http://test/api/v2/notes",
            page=1,
            size=20,
            total=100,
            query_params={"filter[status]": "NEEDS_MORE_RATINGS"},
        )

        assert links.self_ is not None
        assert "filter[status]=NEEDS_MORE_RATINGS" in links.self_
        assert "page[number]=1" in links.self_

        assert links.next_ is not None
        assert "filter[status]=NEEDS_MORE_RATINGS" in links.next_
        assert "page[number]=2" in links.next_


class TestErrorResponseFormatting:
    """Tests for JSON:API error response formatting."""

    def test_error_response_404(self):
        """Test creating a 404 error response."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=404,
            title="Not Found",
            detail="Note abc123 not found",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.status == "404"
        assert error.title == "Not Found"
        assert error.detail == "Note abc123 not found"

        assert error_response.jsonapi["version"] == "1.1"

    def test_error_response_validation(self):
        """Test creating a validation error response."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=422,
            title="Validation Error",
            detail="Field 'status' must be one of: NEEDS_MORE_RATINGS, HELPFUL",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.status == "422"
        assert error.title == "Validation Error"

    def test_error_response_without_detail(self):
        """Test creating an error response without detail."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=500,
            title="Internal Server Error",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.status == "500"
        assert error.title == "Internal Server Error"
        assert error.detail is None

    def test_error_response_with_source_parameter(self):
        """Test error response with source parameter (JSON:API 1.1+)."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=422,
            title="Validation Error",
            detail="Invalid status value",
            source_parameter="filter[status]",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.source is not None
        assert error.source.parameter == "filter[status]"
        assert error.source.pointer is None
        assert error.source.header is None

    def test_error_response_with_source_pointer(self):
        """Test error response with source pointer (JSON:API 1.2)."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=422,
            title="Validation Error",
            detail="Invalid field",
            source_pointer="/data/attributes/summary",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.source is not None
        assert error.source.pointer == "/data/attributes/summary"
        assert error.source.parameter is None
        assert error.source.header is None

    def test_error_response_with_source_header(self):
        """Test error response with source header (JSON:API 1.2)."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=401,
            title="Unauthorized",
            detail="Missing authentication",
            source_header="Authorization",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.source is not None
        assert error.source.header == "Authorization"
        assert error.source.parameter is None
        assert error.source.pointer is None

    def test_error_response_with_multiple_source_fields(self):
        """Test error response with multiple source fields."""
        from src.common.jsonapi import create_error_response

        error_response = create_error_response(
            status_code=422,
            title="Validation Error",
            detail="Invalid request",
            source_parameter="filter[status]",
            source_pointer="/data/attributes/status",
        )

        assert len(error_response.errors) == 1
        error = error_response.errors[0]

        assert error.source is not None
        assert error.source.parameter == "filter[status]"
        assert error.source.pointer == "/data/attributes/status"


class TestJSONAPISchemas:
    """Tests for JSON:API Pydantic schemas."""

    def test_jsonapi_resource_schema(self):
        """Test JSONAPIResource schema structure."""
        from src.common.jsonapi import JSONAPIResource

        resource = JSONAPIResource(
            type="notes",
            id="123",
            attributes={"summary": "Test note", "status": "active"},
        )

        assert resource.type == "notes"
        assert resource.id == "123"
        assert resource.attributes["summary"] == "Test note"
        assert resource.relationships is None
        assert resource.links is None

    def test_jsonapi_resource_with_relationships(self):
        """Test JSONAPIResource with relationships."""
        from src.common.jsonapi import JSONAPIResource

        resource = JSONAPIResource(
            type="notes",
            id="123",
            attributes={"summary": "Test"},
            relationships={"author": {"data": {"type": "users", "id": "user-456"}}},
        )

        assert resource.relationships is not None
        assert resource.relationships["author"]["data"]["type"] == "users"

    def test_jsonapi_list_response_schema(self):
        """Test JSONAPIListResponse schema structure."""
        from src.common.jsonapi import (
            JSONAPILinks,
            JSONAPIListResponse,
            JSONAPIMeta,
            JSONAPIResource,
        )

        resources = [
            JSONAPIResource(type="notes", id="1", attributes={"summary": "Note 1"}),
            JSONAPIResource(type="notes", id="2", attributes={"summary": "Note 2"}),
        ]

        response = JSONAPIListResponse(
            data=resources,
            meta=JSONAPIMeta(count=2),
            links=JSONAPILinks(self_="http://test/notes"),
        )

        assert len(response.data) == 2
        assert response.jsonapi["version"] == "1.1"
        assert response.meta.count == 2
        assert response.links.self_ == "http://test/notes"

    def test_jsonapi_single_response_schema(self):
        """Test JSONAPISingleResponse schema structure."""
        from src.common.jsonapi import JSONAPIResource, JSONAPISingleResponse

        resource = JSONAPIResource(type="notes", id="123", attributes={"summary": "Test"})

        response = JSONAPISingleResponse(
            data=resource,
            links={"self": "http://test/notes/123"},
        )

        assert response.data.id == "123"
        assert response.jsonapi["version"] == "1.1"
        assert response.links["self"] == "http://test/notes/123"

    def test_jsonapi_meta_schema(self):
        """Test JSONAPIMeta schema with all fields."""
        from src.common.jsonapi import JSONAPIMeta

        meta = JSONAPIMeta(count=100, page=3, pages=10)

        assert meta.count == 100
        assert meta.page == 3
        assert meta.pages == 10

    def test_jsonapi_links_serialization(self):
        """Test JSONAPILinks serializes correctly with aliases."""
        from src.common.jsonapi import JSONAPILinks

        links = JSONAPILinks(
            self_="http://test/self",
            first="http://test/first",
            next_="http://test/next",
        )

        data = links.model_dump(by_alias=True)

        assert data["self"] == "http://test/self"
        assert data["first"] == "http://test/first"
        assert data["next"] == "http://test/next"
        assert "self_" not in data
        assert "next_" not in data

    def test_jsonapi_links_describedby(self):
        """Test JSONAPILinks includes JSON:API 1.1 describedby field."""
        from src.common.jsonapi import JSONAPILinks

        links = JSONAPILinks(
            self_="http://test/notes",
            describedby="http://test/openapi.json",
        )

        assert links.describedby == "http://test/openapi.json"

        data = links.model_dump(by_alias=True)
        assert data["describedby"] == "http://test/openapi.json"
        assert data["self"] == "http://test/notes"

    def test_jsonapi_error_schema(self):
        """Test JSONAPIError schema."""
        from src.common.jsonapi import JSONAPIError

        error = JSONAPIError(
            status="404",
            title="Not Found",
            detail="Resource not found",
        )

        assert error.status == "404"
        assert error.title == "Not Found"
        assert error.detail == "Resource not found"

    def test_jsonapi_error_response_schema(self):
        """Test JSONAPIErrorResponse schema."""
        from src.common.jsonapi import JSONAPIError, JSONAPIErrorResponse

        errors = [
            JSONAPIError(status="400", title="Bad Request", detail="Invalid input"),
            JSONAPIError(status="400", title="Bad Request", detail="Missing field"),
        ]

        response = JSONAPIErrorResponse(errors=errors)

        assert len(response.errors) == 2
        assert response.jsonapi["version"] == "1.1"
