"""
Integration tests for platform-agnostic endpoints.

Verifies that community-config and monitored-channels endpoints work for
both Discord and Discourse communities, and that platform-specific rules
(e.g., no auto-create for Discourse) are enforced.

TASK-1400.06.07
"""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

TEST_INTERNAL_SECRET = "test-platform-agnostic-internal-secret-32-min"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def ensure_app_started_and_internal_secret(monkeypatch):
    """Set startup_complete and configure INTERNAL_SERVICE_SECRET for tests.

    ASGITransport triggers the lifespan, but the background init task runs
    concurrently. Tests that make HTTP requests can get 503 if they arrive
    before the background task sets startup_complete=True.

    Also patches INTERNAL_SERVICE_SECRET so X-Platform-Type headers are not
    stripped by InternalHeaderValidationMiddleware (which requires X-Internal-Auth
    from trusted internal services in production).
    """
    app.state.startup_complete = True

    import src.middleware.internal_auth

    monkeypatch.setattr(
        src.middleware.internal_auth.settings,
        "INTERNAL_SERVICE_SECRET",
        TEST_INTERNAL_SECRET,
    )


def _platform_headers(service_account_headers: dict, platform: str) -> dict:
    """Build headers with platform type and internal auth for test requests."""
    return {
        **service_account_headers,
        "X-Platform-Type": platform,
        "X-Internal-Auth": TEST_INTERNAL_SECRET,
    }


@pytest.fixture
async def discord_community_server() -> CommunityServer:
    """Pre-existing Discord community server."""
    unique = uuid4().hex[:10]
    async with get_session_maker()() as db:
        server = CommunityServer(
            platform="discord",
            platform_community_server_id=f"discord_guild_{unique}",
            name=f"Discord Test Server {unique}",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


@pytest.fixture
async def discourse_community_server() -> CommunityServer:
    """Pre-existing Discourse community server."""
    unique = uuid4().hex[:10]
    async with get_session_maker()() as db:
        server = CommunityServer(
            platform="discourse",
            platform_community_server_id=f"discourse_forum_{unique}",
            name=f"Discourse Test Server {unique}",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server


@pytest.fixture
async def service_account_user() -> User:
    """Service account (bot) user for admin operations."""
    unique = uuid4().hex[:10]
    async with get_session_maker()() as db:
        user = User(
            email=f"bot_{unique}@opennotes.local",
            username=f"bot_{unique}",
            hashed_password="hashed_password",
            is_active=True,
            principal_type="agent",
            discord_id=f"bot_discord_{unique}",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def service_account_headers(service_account_user: User) -> dict:
    """JWT headers for service account."""
    from src.auth.auth import create_access_token

    token = create_access_token(
        {
            "sub": str(service_account_user.id),
            "username": service_account_user.username,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_user_for_discord(discord_community_server: CommunityServer) -> User:
    """Regular user who is a community admin in the Discord server."""
    unique = uuid4().hex[:10]
    async with get_session_maker()() as db:
        user = User(
            email=f"discordadmin_{unique}@example.com",
            username=f"discordadmin_{unique}",
            hashed_password="hashed_password",
            is_active=True,
            discord_id=f"discord_admin_{unique}",
        )
        db.add(user)
        await db.flush()

        profile = UserProfile(
            display_name=f"Discord Admin {unique}",
            is_human=True,
            is_active=True,
        )
        db.add(profile)
        await db.flush()

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=user.discord_id,
        )
        db.add(identity)
        await db.flush()

        member = CommunityMember(
            community_id=discord_community_server.id,
            profile_id=profile.id,
            role="admin",
            is_active=True,
        )
        db.add(member)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def admin_headers_for_discord(admin_user_for_discord: User) -> dict:
    from src.auth.auth import create_access_token

    token = create_access_token(
        {
            "sub": str(admin_user_for_discord.id),
            "username": admin_user_for_discord.username,
        }
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_user_for_discourse(discourse_community_server: CommunityServer) -> User:
    """Regular user who is a community admin in the Discourse server."""
    unique = uuid4().hex[:10]
    async with get_session_maker()() as db:
        user = User(
            email=f"discourseadmin_{unique}@example.com",
            username=f"discourseadmin_{unique}",
            hashed_password="hashed_password",
            is_active=True,
            discord_id=f"discourse_admin_discord_{unique}",
        )
        db.add(user)
        await db.flush()

        profile = UserProfile(
            display_name=f"Discourse Admin {unique}",
            is_human=True,
            is_active=True,
        )
        db.add(profile)
        await db.flush()

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=user.discord_id,
        )
        db.add(identity)
        await db.flush()

        member = CommunityMember(
            community_id=discourse_community_server.id,
            profile_id=profile.id,
            role="admin",
            is_active=True,
        )
        db.add(member)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def admin_headers_for_discourse(admin_user_for_discourse: User) -> dict:
    from src.auth.auth import create_access_token

    token = create_access_token(
        {
            "sub": str(admin_user_for_discourse.id),
            "username": admin_user_for_discourse.username,
        }
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests: get_community_server_by_platform_id discourse logic
# ---------------------------------------------------------------------------


class TestDiscourseLookupNoAutoCreate:
    """Discourse community server lookups must NOT auto-create, must return None if missing."""

    @pytest.mark.asyncio
    async def test_discourse_returns_none_when_not_found(self):
        """Looking up a non-existent Discourse community returns None (no auto-create)."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        async with get_session_maker()() as db:
            result = await get_community_server_by_platform_id(
                db=db,
                community_server_id=f"nonexistent_discourse_{uuid4().hex}",
                platform="discourse",
                auto_create=True,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_discourse_auto_create_forced_off(self):
        """Even if auto_create=True is passed, discourse never creates."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        platform_id = f"discourse_should_not_create_{uuid4().hex[:12]}"
        async with get_session_maker()() as db:
            result = await get_community_server_by_platform_id(
                db=db,
                community_server_id=platform_id,
                platform="discourse",
                auto_create=True,
            )
            assert result is None

            from sqlalchemy import select

            check = await db.execute(
                select(CommunityServer).where(
                    CommunityServer.platform_community_server_id == platform_id
                )
            )
            assert check.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_discourse_returns_existing_server(
        self, discourse_community_server: CommunityServer
    ):
        """Discourse lookup returns an existing server correctly."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        async with get_session_maker()() as db:
            result = await get_community_server_by_platform_id(
                db=db,
                community_server_id=discourse_community_server.platform_community_server_id,
                platform="discourse",
                auto_create=False,
            )
        assert result is not None
        assert result.id == discourse_community_server.id
        assert result.platform == "discourse"


class TestDiscordAutoCreateBackwardCompat:
    """Discord community servers still auto-create when requested."""

    @pytest.mark.asyncio
    async def test_discord_auto_creates_when_not_found(self):
        """Discord lookup with auto_create=True creates a new server."""
        from src.auth.community_dependencies import get_community_server_by_platform_id

        platform_id = f"discord_new_guild_{uuid4().hex[:12]}"
        async with get_session_maker()() as db:
            result = await get_community_server_by_platform_id(
                db=db,
                community_server_id=platform_id,
                platform="discord",
                auto_create=True,
            )
            assert result is not None
            assert result.platform == "discord"
            assert result.platform_community_server_id == platform_id
            await db.commit()


# ---------------------------------------------------------------------------
# Tests: community-config endpoint platform-agnostic
# ---------------------------------------------------------------------------


class TestCommunityConfigPlatformAgnostic:
    """community-config GET endpoint respects X-Platform-Type header."""

    @pytest.mark.asyncio
    async def test_get_config_discord_server_with_discord_header(
        self,
        discord_community_server: CommunityServer,
        service_account_headers: dict,
    ):
        """Service account can GET config for a Discord server with X-Platform-Type: discord."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/community-config/{discord_community_server.platform_community_server_id}",
                headers=_platform_headers(service_account_headers, "discord"),
            )
        assert response.status_code == 200
        data = response.json()
        assert "config" in data

    @pytest.mark.asyncio
    async def test_get_config_discourse_server_with_discourse_header(
        self,
        discourse_community_server: CommunityServer,
        service_account_headers: dict,
    ):
        """Service account can GET config for a Discourse server with X-Platform-Type: discourse."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/community-config/{discourse_community_server.platform_community_server_id}",
                headers=_platform_headers(service_account_headers, "discourse"),
            )
        assert response.status_code == 200
        data = response.json()
        assert "config" in data

    @pytest.mark.asyncio
    async def test_get_config_discourse_server_not_found_returns_404(
        self,
        service_account_headers: dict,
    ):
        """GET config for non-existent Discourse server returns 404 (no auto-create)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/community-config/nonexistent_discourse_{uuid4().hex[:12]}",
                headers=_platform_headers(service_account_headers, "discourse"),
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_no_platform_header_defaults_to_discord(
        self,
        discord_community_server: CommunityServer,
        service_account_headers: dict,
    ):
        """GET config without X-Platform-Type header defaults to discord (backward compat)."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/community-config/{discord_community_server.platform_community_server_id}",
                headers=service_account_headers,
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests: monitored-channels endpoint platform-agnostic
# ---------------------------------------------------------------------------


class TestMonitoredChannelsPlatformAgnostic:
    """monitored-channels POST endpoint works for Discourse communities."""

    @pytest.mark.asyncio
    async def test_create_monitored_channel_for_discourse_community(
        self,
        discourse_community_server: CommunityServer,
        service_account_headers: dict,
    ):
        """POST monitored-channel for an existing Discourse community succeeds."""
        from src.fact_checking.dataset_models import FactCheckDataset

        async with get_session_maker()() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(FactCheckDataset).where(FactCheckDataset.slug == "snopes")
            )
            dataset = result.scalar_one_or_none()
            if not dataset:
                dataset = FactCheckDataset(
                    slug="snopes",
                    name="Snopes",
                    description="Fact checking dataset",
                    source_url="https://snopes.com",
                    is_active=True,
                )
                db.add(dataset)
                await db.commit()

        unique_channel_id = f"discourse_ch_{uuid4().hex[:10]}"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/monitored-channels",
                headers=_platform_headers(service_account_headers, "discourse"),
                json={
                    "data": {
                        "type": "monitored-channels",
                        "attributes": {
                            "community_server_id": discourse_community_server.platform_community_server_id,
                            "channel_id": unique_channel_id,
                            "name": "discourse-general",
                            "enabled": True,
                        },
                    }
                },
            )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["data"]["attributes"]["channel_id"] == unique_channel_id

    @pytest.mark.asyncio
    async def test_create_monitored_channel_for_nonexistent_discourse_returns_404(
        self,
        service_account_headers: dict,
    ):
        """POST monitored-channel for non-existent Discourse community returns 404."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/monitored-channels",
                headers=_platform_headers(service_account_headers, "discourse"),
                json={
                    "data": {
                        "type": "monitored-channels",
                        "attributes": {
                            "community_server_id": f"nonexistent_{uuid4().hex[:12]}",
                            "channel_id": f"ch_{uuid4().hex[:8]}",
                            "enabled": True,
                        },
                    }
                },
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_discord_monitored_channel_backward_compat(
        self,
        discord_community_server: CommunityServer,
        service_account_headers: dict,
    ):
        """POST monitored-channel for Discord community still works (backward compat)."""
        from src.fact_checking.dataset_models import FactCheckDataset

        async with get_session_maker()() as db:
            from sqlalchemy import select

            result = await db.execute(
                select(FactCheckDataset).where(FactCheckDataset.slug == "snopes")
            )
            dataset = result.scalar_one_or_none()
            if not dataset:
                dataset = FactCheckDataset(
                    slug="snopes",
                    name="Snopes",
                    description="Fact checking dataset",
                    source_url="https://snopes.com",
                    is_active=True,
                )
                db.add(dataset)
                await db.commit()

        unique_channel_id = f"discord_ch_{uuid4().hex[:10]}"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/monitored-channels",
                headers=_platform_headers(service_account_headers, "discord"),
                json={
                    "data": {
                        "type": "monitored-channels",
                        "attributes": {
                            "community_server_id": discord_community_server.platform_community_server_id,
                            "channel_id": unique_channel_id,
                            "name": "discord-general",
                            "enabled": True,
                        },
                    }
                },
            )
        assert response.status_code == 201, response.text
