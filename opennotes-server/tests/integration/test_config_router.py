import pytest
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app


@pytest.fixture
async def config_test_user():
    """Create a unique test user for config router tests"""
    return {
        "username": "configtestuser",
        "email": "configtest@example.com",
        "password": "TestPassword123!",
        "full_name": "Config Test User",
    }


@pytest.fixture
async def config_registered_user(config_test_user):
    """Create a registered user specifically for config tests"""
    from sqlalchemy import select

    from src.database import async_session_maker
    from src.users.models import User

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json=config_test_user)

        if response.status_code == 400:
            async with async_session_maker() as session:
                stmt = select(User).where(User.username == config_test_user["username"])
                result = await session.execute(stmt)
                existing_user = result.scalar_one()

                return {
                    "id": existing_user.id,
                    "username": existing_user.username,
                    "email": existing_user.email,
                    "full_name": existing_user.full_name,
                    "role": existing_user.role,
                    "is_active": existing_user.is_active,
                    "is_superuser": existing_user.is_superuser,
                }

        assert response.status_code == 201, f"Failed to create config test user: {response.text}"
        return response.json()


@pytest.fixture
async def config_auth_headers(config_registered_user):
    """Generate auth headers for config test user"""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(config_registered_user["id"]),
        "username": config_registered_user["username"],
        "role": config_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def config_auth_client(config_auth_headers):
    """Auth client using config-specific test user"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(config_auth_headers)
        yield client


class TestConfigRouter:
    @pytest.mark.asyncio
    async def test_get_rating_thresholds_authenticated(self, config_auth_client):
        """Test that authenticated users can fetch rating thresholds"""
        response = await config_auth_client.get("/api/v1/config/rating-thresholds")

        assert response.status_code == 200
        data = response.json()

        assert "min_ratings_needed" in data
        assert "min_raters_per_note" in data

        assert isinstance(data["min_ratings_needed"], int)
        assert isinstance(data["min_raters_per_note"], int)

        assert data["min_ratings_needed"] > 0
        assert data["min_raters_per_note"] > 0

    @pytest.mark.asyncio
    async def test_get_rating_thresholds_matches_config(self, config_auth_client):
        """Test that returned values match settings"""
        response = await config_auth_client.get("/api/v1/config/rating-thresholds")

        assert response.status_code == 200
        data = response.json()

        assert data["min_ratings_needed"] == settings.MIN_RATINGS_NEEDED
        assert data["min_raters_per_note"] == settings.MIN_RATERS_PER_NOTE

    @pytest.mark.asyncio
    async def test_get_rating_thresholds_unauthenticated(self):
        """Test that unauthenticated requests are rejected"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/config/rating-thresholds")

            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_rating_thresholds_default_values(self, config_auth_client):
        """Test that values match current configuration"""
        response = await config_auth_client.get("/api/v1/config/rating-thresholds")

        assert response.status_code == 200
        data = response.json()

        assert data["min_ratings_needed"] == settings.MIN_RATINGS_NEEDED
        assert data["min_raters_per_note"] == settings.MIN_RATERS_PER_NOTE
