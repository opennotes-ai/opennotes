"""
Integration tests for Discord platform ID validation through API endpoints.

Task-1028: Tests that the UUID validation for Discord platform IDs is properly
enforced at the API level, not just at the dependency level.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.users.models import User


@pytest.fixture
async def service_account() -> User:
    """Create a test service account for API authentication."""
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
        return user


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


@pytest.mark.asyncio
class TestDiscordPlatformIdApiValidation:
    """Integration tests for Discord platform ID validation at the API level."""

    async def test_lookup_with_uuid_returns_400(self, service_account_headers):
        """API should return 400 when UUID is passed as Discord platform ID."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            uuid_value = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "discord",
                    "platform_community_server_id": uuid_value,
                },
                headers=service_account_headers,
            )

            assert response.status_code == 400
            response_data = response.json()
            assert "Invalid Discord community server ID" in response_data["detail"]
            assert "numeric snowflakes" in response_data["detail"]
            assert uuid_value in response_data["detail"]

    async def test_lookup_with_uppercase_uuid_returns_400(self, service_account_headers):
        """API should return 400 when uppercase UUID is passed as Discord platform ID."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            uuid_value = "1CA684BC-1D2B-4266-B7A5-D1296EE71C65"
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "discord",
                    "platform_community_server_id": uuid_value,
                },
                headers=service_account_headers,
            )

            assert response.status_code == 400
            response_data = response.json()
            assert "Invalid Discord community server ID" in response_data["detail"]

    async def test_lookup_with_valid_snowflake_succeeds(self, service_account_headers):
        """API should accept valid Discord snowflake and return community server."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            snowflake_id = "738146839441965267"
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

    async def test_lookup_uuid_allowed_for_non_discord_platform(self, service_account_headers):
        """API should accept UUID for non-Discord platforms."""
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            uuid_value = "1ca684bc-1d2b-4266-b7a5-d1296ee71c65"
            response = await client.get(
                "/api/v1/community-servers/lookup",
                params={
                    "platform": "slack",
                    "platform_community_server_id": uuid_value,
                },
                headers=service_account_headers,
            )

            assert response.status_code == 200
            response_data = response.json()
            assert response_data["platform"] == "slack"
            assert response_data["platform_community_server_id"] == uuid_value
