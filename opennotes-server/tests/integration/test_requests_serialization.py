"""Integration tests for request endpoint platform_message_id serialization (BigInteger -> string).

Tests the full flow:
1. Database: BigInteger storage for platform_message_id
2. ORM: SQLAlchemy model loads as int
3. Pydantic: RequestResponse schema converts to string
4. JSON: API returns string for JavaScript BigInt compatibility

Verifies that all request endpoints (create, get, list, update) correctly serialize
platform_message_id as string to prevent JavaScript precision loss with large integers.

Updated for v2 JSON:API format endpoints.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def requests_test_user():
    """Create a unique test user for request serialization tests to avoid conflicts"""
    return {
        "username": "requestserializationtestuser",
        "email": "requestserialization@example.com",
        "password": "TestPassword123!",
        "full_name": "Request Serialization Test User",
    }


@pytest.fixture
async def requests_test_community_server():
    """Create a test community server for request serialization tests.

    Returns the platform_id (Discord guild ID) and UUID for API requests.
    """
    from uuid import uuid4

    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "1234567890123456789"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_id=platform_id,
            name="Test Guild for Request Serialization",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_id": platform_id}


@pytest.fixture
async def requests_registered_user(requests_test_user, requests_test_community_server):
    """Create a registered user specifically for request serialization tests.

    Sets a discord_id on the user to enable ownership verification for requests.
    The discord_id is used to match requested_by on requests.

    Also creates UserProfile, UserIdentity, and CommunityMember records
    required by the authorization middleware (task-713).
    """
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=requests_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == requests_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = "requests_serialization_test_discord_id"

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
                community_id=requests_test_community_server["uuid"],
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
async def requests_auth_headers(requests_registered_user):
    """Generate auth headers for request serialization test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(requests_registered_user["id"]),
        "username": requests_registered_user["username"],
        "role": requests_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def requests_auth_client(requests_auth_headers):
    """Auth client using request serialization-specific test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(requests_auth_headers)
        yield client


def make_jsonapi_request_payload(
    request_id, platform_message_id, requested_by, community_server_id
):
    """Helper to create JSON:API formatted request payload"""
    return {
        "data": {
            "type": "requests",
            "attributes": {
                "request_id": request_id,
                "platform_message_id": platform_message_id,
                "requested_by": requested_by,
                "community_server_id": community_server_id,
                "original_message_content": "Test message content",
            },
        }
    }


class TestRequestSerializationCreateEndpoint:
    """Test create_request endpoint platform_message_id serialization"""

    @pytest.mark.asyncio
    async def test_create_request_with_integer_platform_message_id_returns_string(
        self, requests_auth_client
    ):
        """Test that creating request with integer platform_message_id returns string in response"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_create_int_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="1234567890123456789",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )

        response = await requests_auth_client.post("/api/v2/requests", json=request_data)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "1234567890123456789"

    @pytest.mark.asyncio
    async def test_create_request_with_string_platform_message_id_returns_string(
        self, requests_auth_client
    ):
        """Test that creating request with string platform_message_id returns string in response"""
        unique_ts = int(datetime.now(UTC).timestamp() * 1000000)
        request_data = make_jsonapi_request_payload(
            request_id=f"req_create_str_{unique_ts}",
            platform_message_id="8888888888888888888",
            requested_by="test-requester",
            community_server_id=f"{unique_ts}",
        )

        response = await requests_auth_client.post("/api/v2/requests", json=request_data)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "8888888888888888888"

    @pytest.mark.asyncio
    async def test_create_request_with_max_bigint_platform_message_id(self, requests_auth_client):
        """Test with maximum safe BigInteger value (JavaScript Number.MAX_SAFE_INTEGER exceeded)"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_create_max_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="9223372036854775807",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )

        response = await requests_auth_client.post("/api/v2/requests", json=request_data)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "9223372036854775807"

    @pytest.mark.asyncio
    async def test_create_request_verifies_no_500_error(self, requests_auth_client):
        """Test that request creation does not return 500 error (serialization error)"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_create_no500_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="4536233844",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )

        response = await requests_auth_client.post("/api/v2/requests", json=request_data)

        assert response.status_code != 500, f"Should not return 500 error, got: {response.text}"
        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )


class TestRequestSerializationGetEndpoint:
    """Test get_request endpoint platform_message_id serialization"""

    @pytest.mark.asyncio
    async def test_get_request_returns_string_platform_message_id(self, requests_auth_client):
        """Test that getting a request returns platform_message_id as string"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_get_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="5555555555555555555",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )
        create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        response = await requests_auth_client.get(f"/api/v2/requests/{request_id}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "5555555555555555555"

    @pytest.mark.asyncio
    async def test_get_request_verifies_no_500_error(self, requests_auth_client):
        """Test that get request does not return 500 error"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_get_no500_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="7777777777777777777",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )
        create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        response = await requests_auth_client.get(f"/api/v2/requests/{request_id}")

        assert response.status_code != 500, f"Should not return 500 error, got: {response.text}"
        assert response.status_code == 200


class TestRequestSerializationListEndpoint:
    """Test list_requests endpoint platform_message_id serialization"""

    @pytest.mark.asyncio
    async def test_list_requests_returns_string_platform_message_ids(self, requests_auth_client):
        """Test that listing requests returns all platform_message_ids as strings"""
        request_ids = []
        platform_message_ids = ["1111111111111111111", "2222222222222222222", "3333333333333333333"]

        for platform_message_id in platform_message_ids:
            request_data = make_jsonapi_request_payload(
                request_id=f"req_list_{platform_message_id}",
                platform_message_id=platform_message_id,
                requested_by="test-requester",
                community_server_id="1234567890123456789",
            )
            create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
            assert create_response.status_code == 201
            request_ids.append(create_response.json()["data"]["attributes"]["request_id"])

        response = await requests_auth_client.get("/api/v2/requests")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()

        created_requests = [r for r in data["data"] if r["attributes"]["request_id"] in request_ids]
        assert len(created_requests) == 3, f"Expected 3 requests, found {len(created_requests)}"

        for request in created_requests:
            assert isinstance(request["attributes"]["platform_message_id"], str), (
                f"platform_message_id should be string, got {type(request['attributes']['platform_message_id'])}"
            )

        platform_message_id_strs = [
            r["attributes"]["platform_message_id"] for r in created_requests
        ]
        assert "1111111111111111111" in platform_message_id_strs
        assert "2222222222222222222" in platform_message_id_strs
        assert "3333333333333333333" in platform_message_id_strs

    @pytest.mark.asyncio
    async def test_list_requests_with_pagination_serializes_correctly(self, requests_auth_client):
        """Test that paginated list requests returns string platform_message_ids"""
        for i in range(5):
            request_data = make_jsonapi_request_payload(
                request_id=f"req_page_{i}_{int(datetime.now(UTC).timestamp() * 1000000)}",
                platform_message_id=str(1000000000000000000 + i),
                requested_by="test-requester",
                community_server_id="1234567890123456789",
            )
            create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
            assert create_response.status_code == 201

        response = await requests_auth_client.get("/api/v2/requests?page[number]=1&page[size]=3")

        assert response.status_code == 200
        data = response.json()

        for request in data["data"]:
            assert isinstance(request["attributes"]["platform_message_id"], str), (
                f"platform_message_id should be string, got {type(request['attributes']['platform_message_id'])}"
            )

    @pytest.mark.asyncio
    async def test_list_requests_verifies_no_500_error(self, requests_auth_client):
        """Test that list requests does not return 500 error"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_list_no500_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="8888888888888888888",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )
        await requests_auth_client.post("/api/v2/requests", json=request_data)

        response = await requests_auth_client.get("/api/v2/requests")

        assert response.status_code != 500, f"Should not return 500 error, got: {response.text}"
        assert response.status_code == 200


class TestRequestSerializationUpdateEndpoint:
    """Test update_request endpoint platform_message_id serialization"""

    @pytest.mark.asyncio
    async def test_update_request_maintains_string_platform_message_id(
        self, requests_auth_client, requests_registered_user
    ):
        """Test that updating a request maintains platform_message_id as string"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_update_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="6666666666666666666",
            requested_by=requests_registered_user["discord_id"],
            community_server_id="1234567890123456789",
        )
        create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        update_data = {
            "data": {"type": "requests", "id": request_id, "attributes": {"status": "IN_PROGRESS"}}
        }
        response = await requests_auth_client.patch(
            f"/api/v2/requests/{request_id}", json=update_data
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "6666666666666666666"
        assert attrs["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_update_request_verifies_no_500_error(
        self, requests_auth_client, requests_registered_user
    ):
        """Test that update request does not return 500 error"""
        unique_ts = int(datetime.now(UTC).timestamp() * 1000000)
        request_data = make_jsonapi_request_payload(
            request_id=f"req_update_no500_{unique_ts}",
            platform_message_id="8888888888888888886",
            requested_by=requests_registered_user["discord_id"],
            community_server_id=f"{unique_ts}",
        )
        create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        update_data = {
            "data": {"type": "requests", "id": request_id, "attributes": {"status": "COMPLETED"}}
        }
        response = await requests_auth_client.patch(
            f"/api/v2/requests/{request_id}", json=update_data
        )

        assert response.status_code != 500, f"Should not return 500 error, got: {response.text}"
        assert response.status_code == 200


class TestRequestSerializationBulkOperations:
    """Test bulk operations with multiple requests for serialization"""

    @pytest.mark.asyncio
    async def test_multiple_requests_all_serialize_correctly(
        self, requests_auth_client, requests_test_community_server
    ):
        """Test that multiple requests all serialize platform_message_id correctly"""
        test_cases = [
            "1234567890123456789",
            "8888888888888888888",
            "1111111111111111111",
            "2222222222222222222",
            "3333333333333333333",
            "4444444444444444444",
            "5555555555555555555",
            "6666666666666666666",
            "7777777777777777777",
            "8888888888888888887",
        ]

        created_request_ids = []
        base_ts = int(datetime.now(UTC).timestamp() * 1000000)
        for i, platform_message_id in enumerate(test_cases):
            request_data = make_jsonapi_request_payload(
                request_id=f"req_bulk_{i}_{base_ts}",
                platform_message_id=platform_message_id,
                requested_by="test-requester",
                community_server_id=requests_test_community_server["platform_id"],
            )
            create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
            assert create_response.status_code == 201
            created_request_ids.append(create_response.json()["data"]["attributes"]["request_id"])

        response = await requests_auth_client.get("/api/v2/requests?page[size]=100")
        assert response.status_code == 200
        data = response.json()

        created_requests = [
            r for r in data["data"] if r["attributes"]["request_id"] in created_request_ids
        ]
        assert len(created_requests) == 10

        for request in created_requests:
            assert isinstance(request["attributes"]["platform_message_id"], str), (
                f"platform_message_id should be string, got {type(request['attributes']['platform_message_id'])}"
            )

    @pytest.mark.asyncio
    async def test_bulk_operations_verify_no_500_errors(self, requests_auth_client):
        """Test that bulk operations do not return 500 errors"""
        for i in range(5):
            request_data = make_jsonapi_request_payload(
                request_id=f"req_bulk_no500_{i}_{int(datetime.now(UTC).timestamp() * 1000000)}",
                platform_message_id=str(1000000000000000000 + i),
                requested_by="test-requester",
                community_server_id="1234567890123456789",
            )
            create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
            assert create_response.status_code != 500
            assert create_response.status_code == 201

        list_response = await requests_auth_client.get("/api/v2/requests")
        assert list_response.status_code != 500
        assert list_response.status_code == 200


class TestRequestSerializationEdgeCases:
    """Test edge cases for platform_message_id serialization"""

    @pytest.mark.asyncio
    async def test_note_id_also_serializes_as_string(self, requests_auth_client):
        """Test that note_id field is also serialized as string when present"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_note_id_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="1111111111111111111",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )
        create_response = await requests_auth_client.post("/api/v2/requests", json=request_data)
        assert create_response.status_code == 201
        request_id = create_response.json()["data"]["attributes"]["request_id"]

        response = await requests_auth_client.get(f"/api/v2/requests/{request_id}")
        assert response.status_code == 200
        data = response.json()
        attrs = data["data"]["attributes"]

        if attrs.get("note_id") is not None:
            assert isinstance(attrs["note_id"], str), (
                f"note_id should be string, got {type(attrs['note_id'])}"
            )

    @pytest.mark.asyncio
    async def test_small_platform_message_id_also_serializes_as_string(self, requests_auth_client):
        """Test that even small platform_message_id values serialize as string"""
        request_data = make_jsonapi_request_payload(
            request_id=f"req_small_{int(datetime.now(UTC).timestamp() * 1000000)}",
            platform_message_id="123",
            requested_by="test-requester",
            community_server_id="1234567890123456789",
        )

        response = await requests_auth_client.post("/api/v2/requests", json=request_data)

        assert response.status_code == 201
        data = response.json()
        attrs = data["data"]["attributes"]

        assert isinstance(attrs["platform_message_id"], str), (
            f"platform_message_id should be string, got {type(attrs['platform_message_id'])}"
        )
        assert attrs["platform_message_id"] == "123"
