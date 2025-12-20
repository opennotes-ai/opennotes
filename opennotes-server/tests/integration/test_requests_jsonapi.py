"""Tests for JSON:API v2 requests endpoint.

This module contains integration tests for the /api/v2/requests endpoint that follows
the JSON:API 1.1 specification. These tests verify:
- Proper JSON:API response envelope structure
- Filtering capabilities
- Pagination support
- Write operations (POST, PATCH)

Reference: https://jsonapi.org/format/
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def requests_jsonapi_test_user():
    """Create a unique test user for requests JSON:API tests to avoid conflicts"""
    return {
        "username": "requestsjsonapitestuser",
        "email": "requestsjsonapitest@example.com",
        "password": "TestPassword123!",
        "full_name": "Requests JSONAPI Test User",
    }


@pytest.fixture
async def requests_jsonapi_community_server():
    """Create a test community server for requests JSON:API tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_requests_jsonapi_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for Requests JSONAPI",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
async def requests_jsonapi_registered_user(
    requests_jsonapi_test_user, requests_jsonapi_community_server
):
    """Create a registered user for requests JSON:API tests.

    Sets up all required records for community authorization.
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=requests_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == requests_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"requests_jsonapi_discord_{uuid4().hex[:8]}"

            profile = UserProfile(
                display_name=user.full_name or user.username,
                is_human=True,
                is_active=True,
            )
            session.add(profile)
            await session.flush()

            identity = UserIdentity(
                profile_id=profile.id,
                provider="discord",
                provider_user_id=user.discord_id,
            )
            session.add(identity)

            member = CommunityMember(
                community_id=requests_jsonapi_community_server["uuid"],
                profile_id=profile.id,
                role="member",
                is_active=True,
                joined_at=datetime.now(UTC),
            )
            session.add(member)

            await session.commit()
            await session.refresh(user)
            await session.refresh(profile)

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "discord_id": user.discord_id,
                "profile_id": profile.id,
            }


@pytest.fixture
async def requests_jsonapi_auth_headers(requests_jsonapi_registered_user):
    """Generate auth headers for requests JSON:API test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(requests_jsonapi_registered_user["id"]),
        "username": requests_jsonapi_registered_user["username"],
        "role": requests_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def requests_jsonapi_auth_client(requests_jsonapi_auth_headers):
    """Auth client using requests JSON:API test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(requests_jsonapi_auth_headers)
        yield client


@pytest.fixture
def requests_jsonapi_sample_request_data(
    requests_jsonapi_community_server, requests_jsonapi_registered_user
):
    """Sample request data for tests"""
    return {
        "request_id": f"test_request_{int(datetime.now(tz=UTC).timestamp() * 1000000)}",
        "requested_by": requests_jsonapi_registered_user["discord_id"],
        "community_server_id": requests_jsonapi_community_server["platform_id"],
        "original_message_content": "This is a test message content for JSON:API tests",
        "platform_message_id": f"platform_msg_{uuid4().hex[:8]}",
        "platform_channel_id": f"platform_channel_{uuid4().hex[:8]}",
        "platform_author_id": f"platform_author_{uuid4().hex[:8]}",
    }


def make_jsonapi_create_request(request_data: dict) -> dict:
    """Convert flat request data dict to JSON:API request body."""
    return {
        "data": {
            "type": "requests",
            "attributes": {
                "request_id": request_data["request_id"],
                "requested_by": request_data["requested_by"],
                "community_server_id": request_data["community_server_id"],
                "original_message_content": request_data["original_message_content"],
                "platform_message_id": request_data.get("platform_message_id"),
                "platform_channel_id": request_data.get("platform_channel_id"),
                "platform_author_id": request_data.get("platform_author_id"),
            },
        }
    }


class TestJSONAPIRequestsEndpoint:
    """Tests for the JSON:API v2 requests endpoint."""

    def _get_unique_request_data(self, sample_request_data):
        request_data = sample_request_data.copy()
        request_data["request_id"] = (
            f"jsonapi_req_{int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        request_data["platform_message_id"] = f"platform_msg_{uuid4().hex[:8]}"
        return request_data

    @pytest.mark.asyncio
    async def test_list_requests_jsonapi_format(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test GET /api/v2/requests returns proper JSON:API format.

        JSON:API 1.1 requires:
        - 'data' array containing resource objects
        - 'jsonapi' object with version
        - 'links' object for pagination
        - 'meta' object with count
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], list), "'data' must be an array"

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1", "JSON:API version must be 1.1"

        assert "links" in data, "Response must contain 'links' key"

        assert "meta" in data, "Response must contain 'meta' key"
        assert "count" in data["meta"], "'meta' must contain 'count'"

    @pytest.mark.asyncio
    async def test_request_resource_object_structure(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test that request resource objects have correct JSON:API structure.

        Each resource object must contain:
        - 'type': resource type identifier
        - 'id': unique identifier string
        - 'attributes': object containing resource attributes
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) > 0, "Should have at least one request"

        request_resource = data["data"][0]

        assert "type" in request_resource, "Resource must have 'type'"
        assert request_resource["type"] == "requests", "Resource type must be 'requests'"

        assert "id" in request_resource, "Resource must have 'id'"
        assert isinstance(request_resource["id"], str), "Resource id must be a string"

        assert "attributes" in request_resource, "Resource must have 'attributes'"
        attributes = request_resource["attributes"]
        assert "status" in attributes, "Attributes must include 'status'"
        assert "requested_by" in attributes, "Attributes must include 'requested_by'"
        assert "requested_at" in attributes, "Attributes must include 'requested_at'"

    @pytest.mark.asyncio
    async def test_get_single_request_jsonapi_format(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
    ):
        """Test GET /api/v2/requests/{request_id} returns single request in JSON:API format.

        For single resource, 'data' should be an object, not an array.
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        response = await requests_jsonapi_auth_client.get(f"/api/v2/requests/{request_id}")
        assert response.status_code == 200

        data = response.json()

        assert "data" in data, "Response must contain 'data' key"
        assert isinstance(data["data"], dict), "'data' must be an object for single resource"
        assert data["data"]["attributes"]["request_id"] == request_id, (
            "Returned request_id must match requested id"
        )

        assert "jsonapi" in data, "Response must contain 'jsonapi' key"
        assert data["jsonapi"].get("version") == "1.1"

    @pytest.mark.asyncio
    async def test_filter_requests_by_status(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test filtering requests by status using JSON:API filter syntax.

        JSON:API filtering: filter[field]=value
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        filter_query = (
            f"filter[status]=PENDING"
            f"&filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
        )
        response = await requests_jsonapi_auth_client.get(f"/api/v2/requests?{filter_query}")
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        for req in data["data"]:
            assert req["attributes"]["status"] == "PENDING"

    @pytest.mark.asyncio
    async def test_pagination_with_page_params(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test pagination using JSON:API page[number] and page[size] parameters."""
        for i in range(5):
            request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
            request_data["request_id"] = (
                f"jsonapi_pagination_{i}_{int(datetime.now(tz=UTC).timestamp() * 1000000)}"
            )
            jsonapi_body = make_jsonapi_create_request(request_data)
            response = await requests_jsonapi_auth_client.post(
                "/api/v2/requests", json=jsonapi_body
            )
            assert response.status_code == 201

        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?page[number]=1&page[size]=2"
            f"&filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert len(data["data"]) <= 2, "Should return at most 2 requests per page"

        assert "meta" in data
        assert "count" in data["meta"], "Meta should contain total count"
        assert data["meta"]["count"] >= 5, "Total count should be at least 5"

        assert "links" in data
        links = data["links"]
        assert "self" in links or "first" in links, "Links should contain pagination URLs"

    @pytest.mark.asyncio
    async def test_jsonapi_content_type(
        self, requests_jsonapi_auth_client, requests_jsonapi_community_server
    ):
        """Test that response Content-Type is application/vnd.api+json."""
        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
        )
        assert response.status_code == 200

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type, (
            f"Content-Type should be application/vnd.api+json, got: {content_type}"
        )

    @pytest.mark.asyncio
    async def test_request_not_found_jsonapi_error(self, requests_jsonapi_auth_client):
        """Test that 404 errors are returned in JSON:API error format."""
        fake_id = f"nonexistent_request_{uuid4().hex}"
        response = await requests_jsonapi_auth_client.get(f"/api/v2/requests/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "errors" in data, "Error response must contain 'errors' array"
        assert isinstance(data["errors"], list), "'errors' must be an array"

        error = data["errors"][0]
        assert "status" in error or "title" in error, "Error must have status or title"


class TestRequestsWriteOperations:
    """Tests for JSON:API v2 requests write operations (POST, PATCH).

    These tests verify:
    - POST /api/v2/requests creates a request with JSON:API request body
    - PATCH /api/v2/requests/{request_id} updates a request with JSON:API request body
    """

    def _get_unique_request_data(self, sample_request_data):
        request_data = sample_request_data.copy()
        request_data["request_id"] = (
            f"jsonapi_req_{int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        request_data["platform_message_id"] = f"platform_msg_{uuid4().hex[:8]}"
        return request_data

    @pytest.mark.asyncio
    async def test_create_request_jsonapi(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test POST /api/v2/requests creates a request with JSON:API request body.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type' and 'attributes'
        - Response with 201 Created status
        - Response body with 'data' object containing created resource
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)

        request_body = {
            "data": {
                "type": "requests",
                "attributes": {
                    "request_id": request_data["request_id"],
                    "requested_by": request_data["requested_by"],
                    "community_server_id": request_data["community_server_id"],
                    "original_message_content": request_data["original_message_content"],
                    "platform_message_id": request_data["platform_message_id"],
                    "platform_channel_id": request_data["platform_channel_id"],
                    "platform_author_id": request_data["platform_author_id"],
                },
            }
        }

        response = await requests_jsonapi_auth_client.post("/api/v2/requests", json=request_body)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "requests", "Resource type must be 'requests'"
        assert "id" in data["data"], "Resource must have 'id'"
        assert "attributes" in data["data"], "Resource must have 'attributes'"
        assert data["data"]["attributes"]["request_id"] == request_data["request_id"]
        assert data["data"]["attributes"]["status"] == "PENDING"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_request_jsonapi_invalid_type(
        self, requests_jsonapi_auth_client, requests_jsonapi_sample_request_data
    ):
        """Test POST /api/v2/requests rejects invalid resource type."""
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)

        request_body = {
            "data": {
                "type": "invalid_type",
                "attributes": {
                    "request_id": request_data["request_id"],
                    "requested_by": request_data["requested_by"],
                    "community_server_id": request_data["community_server_id"],
                    "original_message_content": request_data["original_message_content"],
                },
            }
        }

        response = await requests_jsonapi_auth_client.post("/api/v2/requests", json=request_body)

        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_update_request_jsonapi(
        self, requests_jsonapi_auth_client, requests_jsonapi_sample_request_data
    ):
        """Test PATCH /api/v2/requests/{request_id} updates a request with JSON:API request body.

        JSON:API 1.1 requires:
        - Request body with 'data' object containing 'type', 'id', and 'attributes'
        - Response with 200 OK status
        - Response body with 'data' object containing updated resource
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201
        created_request = create_response.json()
        request_id = created_request["data"]["attributes"]["request_id"]

        updated_status = "IN_PROGRESS"
        request_body = {
            "data": {
                "type": "requests",
                "id": request_id,
                "attributes": {
                    "status": updated_status,
                },
            }
        }

        response = await requests_jsonapi_auth_client.patch(
            f"/api/v2/requests/{request_id}", json=request_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data, "Response must contain 'data' key"
        assert data["data"]["type"] == "requests"
        assert data["data"]["attributes"]["request_id"] == request_id
        assert data["data"]["attributes"]["status"] == updated_status

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_request_jsonapi_id_mismatch(
        self, requests_jsonapi_auth_client, requests_jsonapi_sample_request_data
    ):
        """Test PATCH /api/v2/requests/{request_id} rejects mismatched IDs."""
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        request_body = {
            "data": {
                "type": "requests",
                "id": "different_request_id",
                "attributes": {
                    "status": "IN_PROGRESS",
                },
            }
        }

        response = await requests_jsonapi_auth_client.patch(
            f"/api/v2/requests/{request_id}", json=request_body
        )

        assert response.status_code == 409, f"Expected 409, got {response.status_code}"


class TestRequestsAdvancedFilters:
    """Tests for advanced filter operators in requests JSON:API endpoint.

    These tests verify the filter operators:
    - filter[status]: Exact match on status
    - filter[requested_by]: Filter by requester
    - filter[requested_at__gte]: Requests created on or after datetime
    - filter[requested_at__lte]: Requests created on or before datetime
    """

    def _get_unique_request_data(self, sample_request_data):
        request_data = sample_request_data.copy()
        request_data["request_id"] = (
            f"jsonapi_req_{int(datetime.now(tz=UTC).timestamp() * 1000000)}"
        )
        request_data["platform_message_id"] = f"platform_msg_{uuid4().hex[:8]}"
        return request_data

    @pytest.mark.asyncio
    async def test_filter_requests_by_requested_by(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test filtering requests by requested_by field."""
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        requested_by = request_data["requested_by"]
        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?"
            f"filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
            f"&filter[requested_by]={requested_by}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        for req in data["data"]:
            assert req["attributes"]["requested_by"] == requested_by

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime:
        """Parse a datetime string, normalizing to naive UTC for comparison."""
        from datetime import datetime as dt

        dt_str = dt_str.replace("Z", "+00:00")
        parsed = dt.fromisoformat(dt_str)
        if parsed.tzinfo is not None:
            parsed = parsed.replace(tzinfo=None)
        return parsed

    @pytest.mark.asyncio
    async def test_filter_requests_by_date_gte(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test filtering requests created on or after a specific date.

        filter[requested_at__gte]=2024-01-01T00:00:00Z should return requests created
        on or after that date.
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        filter_date = "2024-01-01T00:00:00Z"
        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?"
            f"filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
            f"&filter[requested_at__gte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        filter_datetime = self._parse_datetime(filter_date)

        for req in data["data"]:
            requested_at = req["attributes"]["requested_at"]
            if requested_at:
                req_datetime = self._parse_datetime(requested_at)
                assert req_datetime >= filter_datetime, (
                    f"Request requested_at {requested_at} is before filter date {filter_date}"
                )

    @pytest.mark.asyncio
    async def test_filter_requests_by_date_lte(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test filtering requests created on or before a specific date.

        filter[requested_at__lte]=2030-12-31T23:59:59Z should return requests created
        on or before that date.
        """
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        filter_date = "2030-12-31T23:59:59Z"
        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?"
            f"filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
            f"&filter[requested_at__lte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0, "Should return at least one request created before 2030"

    @pytest.mark.asyncio
    async def test_filter_requests_combined(
        self,
        requests_jsonapi_auth_client,
        requests_jsonapi_sample_request_data,
        requests_jsonapi_community_server,
    ):
        """Test combining multiple filter operators with AND logic."""
        request_data = self._get_unique_request_data(requests_jsonapi_sample_request_data)
        jsonapi_body = make_jsonapi_create_request(request_data)
        create_response = await requests_jsonapi_auth_client.post(
            "/api/v2/requests", json=jsonapi_body
        )
        assert create_response.status_code == 201

        filter_date = "2024-01-01T00:00:00Z"
        response = await requests_jsonapi_auth_client.get(
            f"/api/v2/requests?"
            f"filter[community_server_id]={requests_jsonapi_community_server['uuid']}"
            f"&filter[status]=PENDING"
            f"&filter[requested_at__gte]={filter_date}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data

        filter_datetime = self._parse_datetime(filter_date)

        for req in data["data"]:
            assert req["attributes"]["status"] == "PENDING"
            requested_at = req["attributes"]["requested_at"]
            if requested_at:
                req_datetime = self._parse_datetime(requested_at)
                assert req_datetime >= filter_datetime
