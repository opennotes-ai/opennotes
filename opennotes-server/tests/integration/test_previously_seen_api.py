"""Integration tests for previously-seen message detection API (task-523).

Updated for JSON:API v2 endpoints:
- POST /api/v2/previously-seen-messages/check
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.monitored_channel_models import MonitoredChannel
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.llm_config.encryption import EncryptionService
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.main import app
from src.notes.models import Note
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

pytestmark = pytest.mark.asyncio


def _create_previously_seen_check_request(
    message_text: str, guild_id: str, channel_id: str
) -> dict:
    """Create a JSON:API request body for previously seen check."""
    return {
        "data": {
            "type": "previously-seen-check",
            "attributes": {
                "message_text": message_text,
                "guild_id": guild_id,
                "channel_id": channel_id,
            },
        }
    }


@pytest.fixture
async def test_community_server():
    """Create a test community server with OpenAI LLM configuration for previously-seen tests."""
    from src.config import settings

    community_id = None
    llm_config_id = None
    async with get_session_maker()() as session:
        community = CommunityServer(
            platform="discord",
            platform_id="test_guild_prev_seen_123",
            name="Previously Seen Test Guild",
            is_active=True,
        )
        session.add(community)
        await session.flush()

        encryption_service = EncryptionService(settings.ENCRYPTION_MASTER_KEY)
        encrypted_key, key_id, preview = encryption_service.encrypt_api_key("sk-test-key-12345")

        llm_config = CommunityServerLLMConfig(
            community_server_id=community.id,
            provider="openai",
            api_key_encrypted=encrypted_key,
            encryption_key_id=key_id,
            api_key_preview=preview,
            enabled=True,
            settings={},
        )
        session.add(llm_config)
        await session.commit()
        await session.refresh(community)
        await session.refresh(llm_config)
        community_id = community.id
        llm_config_id = llm_config.id

    yield community

    # Cleanup
    if community_id:
        async with get_session_maker()() as session:
            if llm_config_id:
                result = await session.execute(
                    select(CommunityServerLLMConfig).where(
                        CommunityServerLLMConfig.id == llm_config_id
                    )
                )
                config = result.scalar_one_or_none()
                if config:
                    await session.delete(config)

            result = await session.execute(
                select(CommunityServer).where(CommunityServer.id == community_id)
            )
            community = result.scalar_one_or_none()
            if community:
                await session.delete(community)
                await session.commit()


@pytest.fixture
async def test_user_with_auth(test_community_server):
    """Create test user with profile and auth token."""
    from src.auth.auth import create_access_token

    user_id = None
    profile_id = None
    identity_id = None
    membership_id = None

    async with get_session_maker()() as session:
        profile = UserProfile(
            display_name="Prev Seen Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username="prev_seen_testuser",
            email="prev_seen@example.com",
            hashed_password="hashed",
            discord_id="prev_seen_discord_123",
            is_active=True,
        )
        session.add(user)
        await session.flush()

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=user.discord_id,
        )
        session.add(identity)
        await session.flush()

        membership = CommunityMember(
            community_id=test_community_server.id,
            profile_id=profile.id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)

        await session.commit()
        await session.refresh(user)
        await session.refresh(profile)
        await session.refresh(membership)
        await session.refresh(identity)

        user_id = user.id
        profile_id = profile.id
        membership_id = membership.id
        identity_id = identity.id

        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(data=token_data)
        auth_headers = {"Authorization": f"Bearer {access_token}"}

    yield {
        "user": user,
        "profile": profile,
        "headers": auth_headers,
        "community": test_community_server,
    }

    # Cleanup
    if user_id:
        async with get_session_maker()() as session:
            if membership_id:
                result = await session.execute(
                    select(CommunityMember).where(CommunityMember.id == membership_id)
                )
                membership = result.scalar_one_or_none()
                if membership:
                    await session.delete(membership)

            if identity_id:
                result = await session.execute(
                    select(UserIdentity).where(UserIdentity.id == identity_id)
                )
                identity = result.scalar_one_or_none()
                if identity:
                    await session.delete(identity)

            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user:
                await session.delete(user)

            if profile_id:
                result = await session.execute(
                    select(UserProfile).where(UserProfile.id == profile_id)
                )
                profile = result.scalar_one_or_none()
                if profile:
                    await session.delete(profile)

            await session.commit()


@pytest.fixture
async def test_note(test_community_server, test_user_with_auth):
    """Create a test note for previously-seen tests."""
    note_id = None
    async with get_session_maker()() as session:
        note = Note(
            author_participant_id="test_author_123",
            community_server_id=test_community_server.id,
            summary="Test note for previously seen detection 99999990001",
            classification="NOT_MISLEADING",
        )
        session.add(note)
        await session.commit()
        await session.refresh(note)
        note_id = note.id

    yield note

    # Cleanup
    if note_id:
        async with get_session_maker()() as session:
            result = await session.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if note:
                await session.delete(note)
                await session.commit()


@pytest.fixture
async def previously_seen_record(test_community_server, test_note):
    """Create a previously seen message record for testing."""
    record_id = None
    async with get_session_maker()() as session:
        # Create embedding (1536 dimensions)
        embedding = [0.1] * 1536

        record = PreviouslySeenMessage(
            community_server_id=test_community_server.id,
            original_message_id="msg_prev_seen_001",
            published_note_id=test_note.id,
            embedding=embedding,
            embedding_provider="openai",
            embedding_model="text-embedding-3-small",
            extra_metadata={"test": "data"},
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        record_id = record.id

    yield record

    # Cleanup
    if record_id:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(PreviouslySeenMessage.id == record_id)
            )
            record = result.scalar_one_or_none()
            if record:
                await session.delete(record)
                await session.commit()


@pytest.fixture(autouse=True)
def mock_embedding_generation():
    """Mock embedding generation to avoid calling actual OpenAI API."""
    mock_generate = AsyncMock(
        side_effect=lambda db, text, community_server_id: [0.1] * 1536 + [0.2] * 0
    )

    with patch(
        "src.fact_checking.embedding_service.EmbeddingService.generate_embedding",
        mock_generate,
    ):
        yield mock_generate


class TestPreviouslySeenCheckEndpoint:
    """Test /api/v2/previously-seen-messages/check endpoint."""

    async def test_check_endpoint_requires_authentication(self):
        """Test endpoint requires authentication."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id="123",
                channel_id="456",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                json=request_body,
            )

            assert response.status_code == 401

    async def test_check_endpoint_returns_404_for_unknown_guild(self, test_user_with_auth):
        """Test endpoint returns 404 for non-existent guild."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id="nonexistent_guild_999",
                channel_id="123",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 404
            data = response.json()
            assert "errors" in data
            assert any("not found" in str(e.get("detail", "")).lower() for e in data["errors"])

    async def test_check_endpoint_returns_no_action_when_no_matches(self, test_user_with_auth):
        """Test endpoint returns no action flags when no similar messages found."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="completely unique message xyz789",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="123",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["should_auto_publish"] is False
            assert attrs["should_auto_request"] is False
            assert len(attrs["matches"]) == 0
            assert attrs["top_match"] is None

    async def test_check_endpoint_returns_default_thresholds(
        self, test_user_with_auth, previously_seen_record
    ):
        """Test endpoint returns correct default thresholds."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="123",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["autopublish_threshold"] == 0.9
            assert attrs["autorequest_threshold"] == 0.75


class TestPreviouslySeenThresholdConfiguration:
    """Test threshold configuration and channel overrides."""

    async def test_channel_override_autopublish_threshold(
        self, test_user_with_auth, previously_seen_record
    ):
        """Test per-channel autopublish threshold override is respected."""
        channel_id = None
        async with get_session_maker()() as session:
            monitored_channel = MonitoredChannel(
                community_server_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_override_123",
                similarity_threshold=0.75,
                previously_seen_autopublish_threshold=0.95,
                previously_seen_autorequest_threshold=None,
            )
            session.add(monitored_channel)
            await session.commit()
            await session.refresh(monitored_channel)
            channel_id = monitored_channel.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_override_123",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["autopublish_threshold"] == 0.95
            assert attrs["autorequest_threshold"] == 0.75

        if channel_id:
            async with get_session_maker()() as session:
                result = await session.execute(
                    select(MonitoredChannel).where(MonitoredChannel.id == channel_id)
                )
                channel = result.scalar_one_or_none()
                if channel:
                    await session.delete(channel)
                    await session.commit()

    async def test_channel_override_autorequest_threshold(
        self, test_user_with_auth, previously_seen_record
    ):
        """Test per-channel autorequest threshold override is respected."""
        channel_id = None
        async with get_session_maker()() as session:
            monitored_channel = MonitoredChannel(
                community_server_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_autoreq_456",
                similarity_threshold=0.75,
                previously_seen_autopublish_threshold=None,
                previously_seen_autorequest_threshold=0.8,
            )
            session.add(monitored_channel)
            await session.commit()
            await session.refresh(monitored_channel)
            channel_id = monitored_channel.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_autoreq_456",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["autopublish_threshold"] == 0.9
            assert attrs["autorequest_threshold"] == 0.8

        if channel_id:
            async with get_session_maker()() as session:
                result = await session.execute(
                    select(MonitoredChannel).where(MonitoredChannel.id == channel_id)
                )
                channel = result.scalar_one_or_none()
                if channel:
                    await session.delete(channel)
                    await session.commit()

    async def test_channel_override_both_thresholds(
        self, test_user_with_auth, previously_seen_record
    ):
        """Test both thresholds can be overridden independently."""
        channel_id = None
        async with get_session_maker()() as session:
            monitored_channel = MonitoredChannel(
                community_server_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_both_789",
                similarity_threshold=0.75,
                previously_seen_autopublish_threshold=0.88,
                previously_seen_autorequest_threshold=0.72,
            )
            session.add(monitored_channel)
            await session.commit()
            await session.refresh(monitored_channel)
            channel_id = monitored_channel.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="test message",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="test_channel_both_789",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["autopublish_threshold"] == 0.88
            assert attrs["autorequest_threshold"] == 0.72

        if channel_id:
            async with get_session_maker()() as session:
                result = await session.execute(
                    select(MonitoredChannel).where(MonitoredChannel.id == channel_id)
                )
                channel = result.scalar_one_or_none()
                if channel:
                    await session.delete(channel)
                    await session.commit()


class TestCommunityServerScoping:
    """Test community server scoping for previously-seen messages."""

    async def test_messages_scoped_to_guild(self, test_user_with_auth, test_note):
        """Test previously-seen messages are scoped to specific guild."""
        # Create a different community server
        other_community_id = None
        other_note_id = None
        record_id = None

        async with get_session_maker()() as session:
            other_community = CommunityServer(
                platform="discord",
                platform_id="other_guild_999",
                name="Other Guild",
                is_active=True,
            )
            session.add(other_community)
            await session.flush()

            # Create note in other guild
            other_note = Note(
                author_participant_id="test_author_123",
                community_server_id=other_community.id,
                summary="Note in other guild 99999990002",
                classification="NOT_MISLEADING",
            )
            session.add(other_note)
            await session.flush()

            # Create previously seen message in OTHER guild
            embedding = [0.1] * 1536
            record = PreviouslySeenMessage(
                community_server_id=other_community.id,
                original_message_id="msg_other_001",
                published_note_id=other_note.id,
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )
            session.add(record)

            await session.commit()
            await session.refresh(other_community)
            await session.refresh(other_note)
            await session.refresh(record)

            other_community_id = other_community.id
            other_note_id = other_note.id
            record_id = record.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = _create_previously_seen_check_request(
                message_text="similar message",
                guild_id=test_user_with_auth["community"].platform_id,
                channel_id="123",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages/check",
                headers=test_user_with_auth["headers"],
                json=request_body,
            )

            assert response.status_code == 200
            data = response.json()
            attrs = data["data"]["attributes"]
            assert attrs["should_auto_publish"] is False
            assert attrs["should_auto_request"] is False

        # Cleanup
        if record_id:
            async with get_session_maker()() as session:
                result = await session.execute(
                    select(PreviouslySeenMessage).where(PreviouslySeenMessage.id == record_id)
                )
                record = result.scalar_one_or_none()
                if record:
                    await session.delete(record)

                if other_note_id:
                    result = await session.execute(select(Note).where(Note.id == other_note_id))
                    note = result.scalar_one_or_none()
                    if note:
                        await session.delete(note)

                if other_community_id:
                    result = await session.execute(
                        select(CommunityServer).where(CommunityServer.id == other_community_id)
                    )
                    community = result.scalar_one_or_none()
                    if community:
                        await session.delete(community)

                await session.commit()
