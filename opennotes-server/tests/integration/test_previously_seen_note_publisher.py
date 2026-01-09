"""Integration tests for note publisher embedding storage (task-523).

Updated for JSON:API v2 endpoints:
- POST /api/v2/note-publisher-posts - Create post record
- POST /api/v2/previously-seen-messages - Create previously seen record with embedding
"""

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


def _create_note_publisher_post_request(
    note_id: str,
    original_message_id: str,
    channel_id: str,
    community_server_id: str,
    score_at_post: float,
    confidence_at_post: str,
    success: bool,
    error_message: str | None = None,
    auto_post_message_id: str | None = None,
) -> dict:
    """Create a JSON:API request body for note publisher post creation."""
    return {
        "data": {
            "type": "note-publisher-posts",
            "attributes": {
                "note_id": note_id,
                "original_message_id": original_message_id,
                "channel_id": channel_id,
                "community_server_id": community_server_id,
                "score_at_post": score_at_post,
                "confidence_at_post": confidence_at_post,
                "success": success,
                "error_message": error_message,
                "auto_post_message_id": auto_post_message_id,
            },
        }
    }


def _create_previously_seen_message_request(
    community_server_id: str,
    original_message_id: str,
    published_note_id: str,
    embedding: list[float] | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> dict:
    """Create a JSON:API request body for previously seen message creation."""
    return {
        "data": {
            "type": "previously-seen-messages",
            "attributes": {
                "community_server_id": community_server_id,
                "original_message_id": original_message_id,
                "published_note_id": published_note_id,
                "embedding": embedding,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
        }
    }


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
            platform_community_server_id="test_guild_publisher_123",
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
    """Test embedding storage when notes are published.

    In v2 API, note publisher posts and previously seen message records are separate:
    - /api/v2/note-publisher-posts - Records a post attempt
    - /api/v2/previously-seen-messages - Stores embedding for similarity matching

    The caller is responsible for creating both records when a post succeeds.
    """

    async def test_post_record_and_embedding_storage_on_success(self, test_setup):
        """Test successful post creates both post record and embedding storage."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            post_body = _create_note_publisher_post_request(
                note_id=str(test_setup["note"].id),
                original_message_id="msg_publisher_001",
                channel_id="test_channel_123",
                community_server_id=test_setup["community"].platform_community_server_id,
                score_at_post=0.8,
                confidence_at_post="0.9",
                success=True,
            )
            response = await client.post(
                "/api/v2/note-publisher-posts",
                headers=test_setup["headers"],
                json=post_body,
            )

            assert response.status_code == 201
            data = response.json()
            assert "data" in data
            assert data["data"]["type"] == "note-publisher-posts"
            assert "id" in data["data"]

            embedding_body = _create_previously_seen_message_request(
                community_server_id=str(test_setup["community"].id),
                original_message_id="msg_publisher_001",
                published_note_id=str(test_setup["note"].id),
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )
            embed_response = await client.post(
                "/api/v2/previously-seen-messages",
                headers=test_setup["headers"],
                json=embedding_body,
            )

            assert embed_response.status_code == 201

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

    async def test_failed_post_does_not_store_embedding(self, test_setup):
        """Test failed post does NOT create embedding storage record."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            post_body = _create_note_publisher_post_request(
                note_id=str(test_setup["note"].id),
                original_message_id="msg_publisher_failed",
                channel_id="test_channel_123",
                community_server_id=test_setup["community"].platform_community_server_id,
                score_at_post=0.8,
                confidence_at_post="0.9",
                success=False,
                error_message="Rate limited",
            )
            response = await client.post(
                "/api/v2/note-publisher-posts",
                headers=test_setup["headers"],
                json=post_body,
            )

            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_publisher_failed"
                )
            )
            record = result.scalar_one_or_none()

            assert record is None

    async def test_post_without_embedding_succeeds(self, test_setup):
        """Test creating post record without embedding storage succeeds."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            post_body = _create_note_publisher_post_request(
                note_id=str(test_setup["note"].id),
                original_message_id="msg_no_embedding",
                channel_id="test_channel_123",
                community_server_id=test_setup["community"].platform_community_server_id,
                score_at_post=0.8,
                confidence_at_post="0.9",
                success=True,
            )
            response = await client.post(
                "/api/v2/note-publisher-posts",
                headers=test_setup["headers"],
                json=post_body,
            )

            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_no_embedding"
                )
            )
            record = result.scalar_one_or_none()

            assert record is None

    async def test_embedding_stores_provider_and_model(self, test_setup):
        """Test embedding storage includes provider and model metadata."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            embedding_body = _create_previously_seen_message_request(
                community_server_id=str(test_setup["community"].id),
                original_message_id="msg_with_metadata",
                published_note_id=str(test_setup["note"].id),
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages",
                headers=test_setup["headers"],
                json=embedding_body,
            )

            assert response.status_code == 201

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

    async def test_embedding_stores_community_server_reference(self, test_setup):
        """Test embedding storage stores correct community_server_id."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            embedding_body = _create_previously_seen_message_request(
                community_server_id=str(test_setup["community"].id),
                original_message_id="msg_server_ref",
                published_note_id=str(test_setup["note"].id),
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages",
                headers=test_setup["headers"],
                json=embedding_body,
            )

            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_server_ref"
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.community_server_id == test_setup["community"].id

    async def test_embedding_stores_published_note_reference(self, test_setup):
        """Test embedding storage stores correct published_note_id."""
        embedding = [0.1] * 1536
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            embedding_body = _create_previously_seen_message_request(
                community_server_id=str(test_setup["community"].id),
                original_message_id="msg_note_ref",
                published_note_id=str(test_setup["note"].id),
                embedding=embedding,
                embedding_provider="openai",
                embedding_model="text-embedding-3-small",
            )
            response = await client.post(
                "/api/v2/previously-seen-messages",
                headers=test_setup["headers"],
                json=embedding_body,
            )

            assert response.status_code == 201

        async with get_session_maker()() as session:
            result = await session.execute(
                select(PreviouslySeenMessage).where(
                    PreviouslySeenMessage.original_message_id == "msg_note_ref"
                )
            )
            record = result.scalar_one_or_none()

            assert record is not None
            assert record.published_note_id == test_setup["note"].id
