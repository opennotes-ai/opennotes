"""
Integration tests for community server platform ID validation through API endpoints.

Task-1028: Tests that circular reference validation (preventing use of existing
CommunityServer UUIDs as platform IDs) is properly enforced at the API level.
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.llm_config.models import CommunityServer
from src.users.models import User


def generate_snowflake() -> str:
    """Generate a unique snowflake-like ID for testing."""
    return str(int(uuid4().hex[:16], 16) % (10**18) + 10**17)


@pytest.fixture
async def service_account():
    """Create a test service account for API authentication.

    Uses yield pattern to ensure cleanup after test completes.
    """
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        user = User(
            email="discord-id-test-service@opennotes.local",
            username="discord-id-test-service",
            hashed_password="hashed_password",
            is_active=True,
            role="user",
            is_service_account=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        user_id = user.id

    yield user

    async with async_session_maker() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


@pytest.fixture
async def service_account_headers(service_account: User):
    """Generate valid JWT token for service account authenticated requests."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(service_account.id),
        "username": service_account.username,
        "role": service_account.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def existing_community_server():
    """Create a community server in the database for circular reference tests.

    Uses yield pattern to ensure cleanup after test completes.
    """
    from src.database import get_session_maker

    async_session_maker = get_session_maker()
    async with async_session_maker() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id=generate_snowflake(),
            name="Test Server for Circular Reference",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        server_id = server.id

    yield server

    async with async_session_maker() as db:
        await db.execute(delete(CommunityServer).where(CommunityServer.id == server_id))
        await db.commit()


@pytest.mark.asyncio
class TestCircularReferenceApiValidation:
    """Integration tests for circular reference prevention at the API level."""

    async def test_lookup_with_existing_uuid_returns_400(
        self, service_account_headers, existing_community_server
    ):
        """API should return 400 when existing CommunityServer UUID is passed as platform ID."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "discord",
                    "platform_community_server_id": str(existing_community_server.id),
                },
                headers=service_account_headers,
            )

            assert response.status_code == 400
            response_data = response.json()
            assert "matches an existing community server's internal UUID" in response_data["detail"]
            assert str(existing_community_server.id) in response_data["detail"]

    async def test_lookup_with_uppercase_existing_uuid_returns_400(
        self, service_account_headers, existing_community_server
    ):
        """API should return 400 when uppercase existing UUID is passed as platform ID."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            uuid_upper = str(existing_community_server.id).upper()
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "discord",
                    "platform_community_server_id": uuid_upper,
                },
                headers=service_account_headers,
            )

            assert response.status_code == 400
            response_data = response.json()
            assert "matches an existing community server's internal UUID" in response_data["detail"]

    async def test_lookup_with_valid_snowflake_succeeds(self, service_account_headers):
        """API should accept valid Discord snowflake and return community server."""
        from src.database import get_session_maker
        from src.main import app

        snowflake_id = generate_snowflake()
        created_server_id = None

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/community-servers/lookup",
                    params={
                        "platform": "discord",
                        "platform_community_server_id": snowflake_id,
                    },
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["platform"] == "discord"
                assert response_data["platform_community_server_id"] == snowflake_id
                assert "id" in response_data
                created_server_id = response_data["id"]
        finally:
            if created_server_id:
                async_session_maker = get_session_maker()
                async with async_session_maker() as db:
                    await db.execute(
                        delete(CommunityServer).where(
                            CommunityServer.platform_community_server_id == snowflake_id
                        )
                    )
                    await db.commit()

    async def test_lookup_non_existing_uuid_allowed_for_slack(self, service_account_headers):
        """API should accept UUID for non-Discord platforms when it doesn't match existing PKs."""
        from src.database import get_session_maker
        from src.main import app

        non_existing_uuid = str(uuid4())
        created_server_id = None

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/community-servers/lookup",
                    params={
                        "platform": "slack",
                        "platform_community_server_id": non_existing_uuid,
                    },
                    headers=service_account_headers,
                )

                assert response.status_code == 200
                response_data = response.json()
                assert response_data["platform"] == "slack"
                assert response_data["platform_community_server_id"] == non_existing_uuid
                created_server_id = response_data["id"]
        finally:
            if created_server_id:
                async_session_maker = get_session_maker()
                async with async_session_maker() as db:
                    await db.execute(
                        delete(CommunityServer).where(
                            CommunityServer.platform_community_server_id == non_existing_uuid
                        )
                    )
                    await db.commit()

    async def test_lookup_existing_uuid_rejected_for_any_platform(
        self, service_account_headers, existing_community_server
    ):
        """API should reject existing CommunityServer UUID regardless of platform param."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "slack",
                    "platform_community_server_id": str(existing_community_server.id),
                },
                headers=service_account_headers,
            )

            assert response.status_code == 400
            response_data = response.json()
            assert "matches an existing community server's internal UUID" in response_data["detail"]


@pytest.mark.asyncio
class TestMonitoredChannelPlatformIdValidation:
    """Integration tests for monitored channel creation with platform ID validation.

    Task-1028: Tests that passing a community_server UUID (primary key) as the
    platform ID is properly rejected with 400 error, preventing duplicate
    community server creation.
    """

    async def test_create_monitored_channel_with_existing_uuid_is_rejected(
        self, service_account_headers
    ):
        """API should reject creating monitored channel with community server UUID as platform ID.

        This tests the bug scenario where a client accidentally passes the community_server
        UUID (internal PK) instead of the Discord guild ID (platform_community_server_id).
        The API returns 400 with an error explaining the circular reference issue.
        """
        from src.database import get_session_maker
        from src.main import app

        async_session_maker = get_session_maker()
        platform_id = generate_snowflake()
        community_uuid = None

        async with async_session_maker() as db:
            community = CommunityServer(
                platform="discord",
                platform_community_server_id=platform_id,
                name="Test Community for UUID Validation",
                is_active=True,
                is_public=True,
            )
            db.add(community)
            await db.commit()
            await db.refresh(community)
            community_uuid = str(community.id)

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v2/monitored-channels",
                    json={
                        "data": {
                            "type": "monitored-channels",
                            "attributes": {
                                "community_server_id": community_uuid,
                                "channel_id": generate_snowflake(),
                            },
                        }
                    },
                    headers={
                        **service_account_headers,
                        "Content-Type": "application/vnd.api+json",
                    },
                )

                assert response.status_code == 400
                response_data = response.json()
                assert "errors" in response_data
                error_detail = response_data["errors"][0]["detail"]
                assert "matches an existing community server's internal UUID" in error_detail
                assert community_uuid in error_detail

        finally:
            async with async_session_maker() as db:
                await db.execute(
                    delete(CommunityServer).where(
                        CommunityServer.platform_community_server_id == platform_id
                    )
                )
                await db.commit()

    async def test_create_monitored_channel_with_valid_snowflake_succeeds(
        self, service_account_headers
    ):
        """API should accept valid Discord snowflakes and create monitored channel.

        This tests the happy path where a client passes valid Discord snowflake IDs
        for both community_server_id and channel_id.
        """
        from src.database import get_session_maker
        from src.main import app

        async_session_maker = get_session_maker()
        community_server_snowflake = generate_snowflake()
        channel_snowflake = generate_snowflake()

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v2/monitored-channels",
                    json={
                        "data": {
                            "type": "monitored-channels",
                            "attributes": {
                                "community_server_id": community_server_snowflake,
                                "channel_id": channel_snowflake,
                            },
                        }
                    },
                    headers={
                        **service_account_headers,
                        "Content-Type": "application/vnd.api+json",
                    },
                )

                assert response.status_code == 201
                response_data = response.json()
                assert "data" in response_data
                assert response_data["data"]["type"] == "monitored-channels"
                attrs = response_data["data"]["attributes"]
                assert attrs["channel_id"] == channel_snowflake

        finally:
            async with async_session_maker() as db:
                await db.execute(
                    delete(MonitoredChannel).where(MonitoredChannel.channel_id == channel_snowflake)
                )
                await db.execute(
                    delete(CommunityServer).where(
                        CommunityServer.platform_community_server_id == community_server_snowflake
                    )
                )
                await db.commit()
