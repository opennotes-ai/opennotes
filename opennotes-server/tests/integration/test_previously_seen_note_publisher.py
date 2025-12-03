"""Integration tests for note publisher embedding storage (task-523)."""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.previously_seen_models import PreviouslySeenMessage
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_setup():
    """Create test community, user, and note for embedding storage tests."""
    from src.auth.auth import create_access_token

    community_id = None
    user_id = None
    profile_id = None
    identity_id = None
    membership_id = None
    note_id = None

    async with get_session_maker()() as session:
        # Create community server
        community = CommunityServer(
            platform="discord",
            platform_id="test_guild_publisher_123",
            name="Publisher Test Guild",
            is_active=True,
        )
        session.add(community)
        await session.flush()

        # Create user with profile
        profile = UserProfile(
            display_name="Publisher Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username="publisher_testuser",
            email="publisher@example.com",
            hashed_password="hashed",
            discord_id="publisher_discord_123",
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
            community_id=community.id,
            profile_id=profile.id,
            role="member",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        session.add(membership)
        await session.flush()

        # Create test note
        note = Note(
            author_participant_id="test_author_123",
            community_server_id=community.id,
            summary="Test note for embedding storage 99999990100",
            classification="NOT_MISLEADING",
        )
        session.add(note)

        await session.commit()
        await session.refresh(community)
        await session.refresh(user)
        await session.refresh(profile)
        await session.refresh(membership)
        await session.refresh(identity)
        await session.refresh(note)

        community_id = community.id
        user_id = user.id
        profile_id = profile.id
        membership_id = membership.id
        identity_id = identity.id
        note_id = note.id

        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(data=token_data)
        auth_headers = {"Authorization": f"Bearer {access_token}"}

    yield {
        "community": community,
        "user": user,
        "note": note,
        "headers": auth_headers,
    }

    # Cleanup
    if note_id:
        async with get_session_maker()() as session:
            # Delete previously seen messages first (foreign key constraint)
            prev_seen_records = (
                (
                    await session.execute(
                        select(PreviouslySeenMessage).where(
                            PreviouslySeenMessage.published_note_id == note_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            for record in prev_seen_records:
                await session.delete(record)

            await session.flush()

            result = await session.execute(select(Note).where(Note.id == note_id))
            note = result.scalar_one_or_none()
            if note:
                await session.delete(note)

            await session.flush()

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

            if user_id:
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

            if community_id:
                result = await session.execute(
                    select(CommunityServer).where(CommunityServer.id == community_id)
                )
                community = result.scalar_one_or_none()
                if community:
                    await session.delete(community)

            await session.commit()


class TestNotePublisherEmbeddingStorage:
    """Test embedding storage when notes are published."""

    async def test_record_endpoint_stores_embedding_on_success(self, test_setup):
        """Test /note-publisher/record stores embedding when post succeeds."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_publisher_001",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": True,
                    "messageEmbedding": embedding,
                    "embeddingProvider": "openai",
                    "embeddingModel": "text-embedding-3-small",
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert "id" in data
            assert "recorded_at" in data

        # Verify embedding was stored
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.published_note_id == test_setup["note"].id
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.original_message_id == "msg_publisher_001"
            assert record.embedding is not None
            assert len(record.embedding) == 1536
            assert record.embedding_provider == "openai"
            assert record.embedding_model == "text-embedding-3-small"

    async def test_record_endpoint_does_not_store_embedding_on_failure(self, test_setup):
        """Test /note-publisher/record does NOT store embedding when post fails."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_publisher_failed",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": False,  # Failed post
                    "failureReason": "Rate limited",
                    "messageEmbedding": embedding,
                    "embeddingProvider": "openai",
                    "embeddingModel": "text-embedding-3-small",
                },
            )

            assert response.status_code == 201

        # Verify NO embedding was stored for failed post
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_publisher_failed"
                )
            )
            record = result.scalar_one_or_none()

            assert record is None  # Should not store embedding for failed posts

    async def test_record_endpoint_handles_missing_embedding_gracefully(self, test_setup):
        """Test /note-publisher/record handles missing embedding gracefully."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_no_embedding",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": True,
                    # No embedding fields provided
                },
            )

            # Should still succeed (embedding is optional)
            assert response.status_code == 201

        # Verify no embedding was stored (graceful handling)
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_no_embedding"
                )
            )
            record = result.scalar_one_or_none()

            assert record is None  # No embedding, so no record stored

    async def test_record_endpoint_stores_embedding_with_metadata(self, test_setup):
        """Test /note-publisher/record can include extra metadata."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_with_metadata",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": True,
                    "messageEmbedding": embedding,
                    "embeddingProvider": "openai",
                    "embeddingModel": "text-embedding-3-small",
                },
            )

            assert response.status_code == 201

        # Verify metadata is stored
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_with_metadata"
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.embedding_provider == "openai"
            assert record.embedding_model == "text-embedding-3-small"

    async def test_record_endpoint_stores_community_server_reference(self, test_setup):
        """Test /note-publisher/record stores correct community_server_id."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_server_ref",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": True,
                    "messageEmbedding": embedding,
                    "embeddingProvider": "openai",
                    "embeddingModel": "text-embedding-3-small",
                },
            )

            assert response.status_code == 201

        # Verify community_server_id is correct
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_server_ref"
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.community_server_id == test_setup["community"].id

    async def test_record_endpoint_stores_published_note_reference(self, test_setup):
        """Test /note-publisher/record stores correct published_note_id."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/note-publisher/record",
                headers=test_setup["headers"],
                json={
                    "noteId": str(test_setup["note"].id),
                    "originalMessageId": "msg_note_ref",
                    "channelId": "test_channel_123",
                    "guildId": test_setup["community"].platform_id,
                    "scoreAtPost": 0.8,
                    "confidenceAtPost": "0.9",
                    "success": True,
                    "messageEmbedding": embedding,
                    "embeddingProvider": "openai",
                    "embeddingModel": "text-embedding-3-small",
                },
            )

            assert response.status_code == 201

        # Verify published_note_id is correct
        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_note_ref"
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.published_note_id == test_setup["note"].id
