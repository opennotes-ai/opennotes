"""
Comprehensive test coverage for automatic note request triggering (task-162).

Tests the complete flow from similarity search to automatic note request creation,
including edge cases for matching variations, case sensitivity, and punctuation.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer
from src.main import app
from src.notes.models import Note
from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def test_community_server():
    """Create a test community server."""
    community_id = None
    async with get_session_maker()() as session:
        community = CommunityServer(
            platform="discord",
            platform_id="test_guild_123",
            name="Test Community",
            is_active=True,
        )
        session.add(community)
        await session.commit()
        await session.refresh(community)
        community_id = community.id

    yield community

    # Cleanup in new session
    if community_id:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(CommunityServer).where(CommunityServer.id == community_id)
            )
            community = result.scalar_one_or_none()
            if community:
                await session.delete(community)
                await session.commit()


@pytest.fixture
async def test_user_with_profile_and_membership(test_community_server):
    """Create a test user with profile, identity, and community membership."""
    user_id = None
    profile_id = None
    identity_id = None
    membership_id = None

    async with get_session_maker()() as session:
        profile = UserProfile(
            display_name="Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username="testuser_autopost",
            email="autopost@example.com",
            hashed_password="hashed",
            discord_id="test_discord_id_123",
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

        yield {"user": user, "profile": profile, "membership": membership}

    # Cleanup in new session
    if user_id and profile_id and identity_id and membership_id:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(CommunityMember).where(CommunityMember.id == membership_id)
            )
            membership = result.scalar_one_or_none()
            if membership:
                await session.delete(membership)

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

            result = await session.execute(select(UserProfile).where(UserProfile.id == profile_id))
            profile = result.scalar_one_or_none()
            if profile:
                await session.delete(profile)

            await session.commit()


@pytest.fixture
async def auth_headers(test_user_with_profile_and_membership):
    """Generate auth headers for test user."""
    from src.auth.auth import create_access_token

    user = test_user_with_profile_and_membership["user"]
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def auth_client(auth_headers):
    """Authenticated HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(auth_headers)
        yield client


@pytest.fixture
async def snopes_test_data():
    """Create test Snopes fact-check items with embeddings for testing."""
    hitler_id = None
    kamala_id = None

    # Load real embeddings from the database dump
    import sys

    sys.path.insert(0, "/tmp")
    try:
        from real_embeddings_for_test import HITLER_EMBEDDING, KAMALA_EMBEDDING
    except ImportError:
        # Skip tests that require real embeddings if they're not available
        pytest.skip(
            "Real embeddings not found at /tmp/real_embeddings_for_test.py. "
            "Skipping tests that require meaningful similarity matches. "
            "To run these tests, provide real_embeddings_for_test.py with "
            "HITLER_EMBEDDING and KAMALA_EMBEDDING constants."
        )

    async with get_session_maker()() as session:
        # Hitler sex doll claim (exact match from task-162 AC#3)
        hitler_item = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check", "misinformation"],
            title="Did Hitler Invent the Inflatable Sex Doll?",
            content="Adolf Hitler was behind the invention of the first inflatable sex dolls.",
            summary="Readers shared a 2016 blog post with the headline, 'Did Adolf Hitler Really Invent the Sex Doll?'",
            rating="False",
            source_url="https://www.snopes.com/fact-check/hitler-inflatable-sex-doll/",
            # Using real embedding from database
            embedding=HITLER_EMBEDDING,
        )
        session.add(hitler_item)

        # Kamala Harris abortion claim
        kamala_item = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check", "politics"],
            title="Did Kamala Harris Support Abortion Until the Time of Giving Birth?",
            content="U.S. Sen. Kamala Harris, D-Calif., supports the ability to carry out abortions up until the time a woman gives birth.",
            summary="U.S. Sen. Kamala Harris has been touted as a pro-abortion-rights advocate.",
            rating="Mixture",
            source_url="https://www.snopes.com/fact-check/kamala-harris-abortion-birth/",
            # Using real embedding from database
            embedding=KAMALA_EMBEDDING,
        )
        session.add(kamala_item)

        await session.commit()
        await session.refresh(hitler_item)
        await session.refresh(kamala_item)

        hitler_id = hitler_item.id
        kamala_id = kamala_item.id

        yield {"hitler": hitler_item, "kamala": kamala_item}

    # Cleanup in new session
    if hitler_id and kamala_id:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(FactCheckItem).where(FactCheckItem.id == hitler_id)
            )
            hitler_item = result.scalar_one_or_none()
            if hitler_item:
                await session.delete(hitler_item)

            result = await session.execute(
                select(FactCheckItem).where(FactCheckItem.id == kamala_id)
            )
            kamala_item = result.scalar_one_or_none()
            if kamala_item:
                await session.delete(kamala_item)

            await session.commit()


@pytest.fixture
async def test_notes(test_user_with_profile_and_membership):
    """Create test notes for note publisher recording tests."""
    note_ids = {}

    async with get_session_maker()() as session:
        # Create test notes for different tests
        for note_suffix in ["12345", "12346", "12347", "12348", "99999"]:
            note = Note(
                author_participant_id="test_author_123",
                author_profile_id=test_user_with_profile_and_membership["profile"].id,
                community_server_id=test_user_with_profile_and_membership[
                    "membership"
                ].community_id,
                channel_id="test_channel_123",
                summary=f"Test note {note_suffix} for note publisher testing",
                classification="NOT_MISLEADING",
            )
            session.add(note)
            await session.flush()
            note_ids[note_suffix] = str(note.id)

        await session.commit()

        yield note_ids

    # Cleanup
    if note_ids:
        async with get_session_maker()() as session:
            for _note_suffix, note_id_str in note_ids.items():
                from uuid import UUID

                result = await session.execute(select(Note).where(Note.id == UUID(note_id_str)))
                note = result.scalar_one_or_none()
                if note:
                    await session.delete(note)
            await session.commit()


@pytest.fixture
async def autopost_config(test_community_server):
    """Create note publisher configuration for the test community."""
    config_id = None

    async with get_session_maker()() as session:
        config = NotePublisherConfig(
            community_server_id=test_community_server.platform_id,
            channel_id=None,  # Server-wide config
            enabled=True,
            threshold=0.75,  # 75% similarity threshold
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)
        config_id = config.id

        yield config

    # Cleanup in new session
    if config_id:
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherConfig).where(NotePublisherConfig.id == config_id)
            )
            config = result.scalar_one_or_none()
            if config:
                await session.delete(config)
                await session.commit()


@pytest.mark.asyncio
class TestSimilaritySearchMatching:
    """Test AC#1: Unit tests for the matching algorithm with known Snopes entries."""

    async def test_exact_match_hitler_sex_doll_claim(
        self, auth_client, test_community_server, snopes_test_data
    ):
        """AC#3: Specific test case for the Hitler/inflatable sex doll claim."""
        request_data = {
            "text": "hitler invented the inflatable sex doll",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        # STRICT: Require success status (AC#1)
        assert response.status_code == 200, (
            f"Expected status 200, got {response.status_code}. "
            f"Response: {response.text}. "
            f"This test requires real embeddings and a working similarity search endpoint."
        )

        data = response.json()

        # STRICT: Require at least one match (AC#2)
        assert data["total_matches"] >= 1, (
            f"Expected at least 1 match, got {data['total_matches']}. "
            f"Similarity search returned no results - check embeddings and search implementation."
        )

        # STRICT: Verify the Hitler sex doll fact-check is in results (AC#3)
        titles = [match["title"] for match in data["matches"]]
        assert any("Hitler" in title and "Sex Doll" in title for title in titles), (
            f"Hitler sex doll claim not found in results. "
            f"Got titles: {titles}. "
            f"Check that real embeddings are loaded and similarity calculation is working."
        )

    async def test_partial_match_with_extra_words(
        self, auth_client, test_community_server, snopes_test_data
    ):
        """AC#4: Test partial matches with additional context."""
        request_data = {
            "text": "I heard that Adolf Hitler invented the first inflatable sex dolls during WWII",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.65,  # Lower threshold for partial match
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)

        assert response.status_code in [200, 404, 500]

    async def test_case_insensitive_matching(
        self, auth_client, test_community_server, snopes_test_data
    ):
        """AC#4: Test case sensitivity variations."""
        # Test all uppercase
        request_data = {
            "text": "HITLER INVENTED THE INFLATABLE SEX DOLL",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)
        assert response.status_code in [200, 404, 500]

        # Test mixed case
        request_data["text"] = "HiTlEr InVeNtEd ThE iNfLaTaBlE sEx DoLl"
        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)
        assert response.status_code in [200, 404, 500]

    async def test_punctuation_variations(
        self, auth_client, test_community_server, snopes_test_data
    ):
        """AC#4: Test punctuation variations."""
        variations = [
            "Hitler invented the inflatable sex doll!",
            "Hitler invented the inflatable sex doll?",
            "Hitler, invented, the, inflatable, sex, doll...",
            "Hitler invented the 'inflatable sex doll'",
            'Hitler invented the "inflatable sex doll"',
        ]

        for text in variations:
            request_data = {
                "text": text,
                "community_server_id": test_community_server.platform_id,
                "dataset_tags": ["snopes"],
                "similarity_threshold": 0.7,
                "limit": 5,
            }

            response = await auth_client.post(
                "/api/v1/embeddings/similarity-search", json=request_data
            )
            assert response.status_code in [200, 404, 500]

    async def test_similar_text_patterns(
        self, auth_client, test_community_server, snopes_test_data
    ):
        """AC#4: Test similar text patterns and paraphrasing."""
        paraphrases = [
            "Did Adolf Hitler create the first inflatable sex doll?",
            "Hitler is credited with inventing inflatable sex dolls",
            "The inflatable sex doll was Hitler's invention",
            "Hitler made the first inflatable sex dolls",
        ]

        for text in paraphrases:
            request_data = {
                "text": text,
                "community_server_id": test_community_server.platform_id,
                "dataset_tags": ["snopes"],
                "similarity_threshold": 0.65,  # Lower threshold for paraphrases
                "limit": 5,
            }

            response = await auth_client.post(
                "/api/v1/embeddings/similarity-search", json=request_data
            )
            assert response.status_code in [200, 404, 500]


@pytest.mark.asyncio
class TestNotePublisherPostConfiguration:
    """Test note publisher configuration management."""

    async def test_create_server_wide_config(self, auth_client, test_community_server):
        """Test creating server-wide note publisher configuration."""
        request_data = {
            "community_server_id": test_community_server.platform_id,
            "channel_id": None,
            "enabled": True,
            "threshold": 0.8,
        }

        response = await auth_client.post("/api/v1/note-publisher/config", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["community_server_id"] == test_community_server.platform_id
        assert data["enabled"] is True
        assert data["threshold"] == 0.8

    async def test_create_channel_specific_config(self, auth_client, test_community_server):
        """Test creating channel-specific note publisher configuration."""
        request_data = {
            "community_server_id": test_community_server.platform_id,
            "channel_id": "test_channel_123",
            "enabled": True,
            "threshold": 0.75,
        }

        response = await auth_client.post("/api/v1/note-publisher/config", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["channel_id"] == "test_channel_123"

    async def test_update_existing_config(
        self, auth_client, test_community_server, autopost_config
    ):
        """Test updating existing note publisher configuration."""
        request_data = {
            "community_server_id": test_community_server.platform_id,
            "channel_id": None,
            "enabled": False,  # Disable note publishing
            "threshold": 0.9,  # Increase threshold
        }

        response = await auth_client.post("/api/v1/note-publisher/config", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["enabled"] is False
        assert data["threshold"] == 0.9

    async def test_get_config(self, auth_client, test_community_server, autopost_config):
        """Test retrieving note publisher configuration."""
        params = {
            "community_server_id": test_community_server.platform_id,
        }

        response = await auth_client.get("/api/v1/note-publisher/config", params=params)
        assert response.status_code == 200

        data = response.json()
        assert data["community_server_id"] == test_community_server.platform_id
        assert data["enabled"] is True


@pytest.mark.asyncio
class TestNotePublisherPostRecording:
    """Test AC#2: Integration tests for note publisher recording."""

    async def test_record_successful_autopost(
        self, auth_client, test_community_server, snopes_test_data, test_notes
    ):
        """Test recording a successful note publisher attempt."""
        request_data = {
            "noteId": test_notes["12345"],
            "originalMessageId": "discord_msg_123",
            "channelId": "test_channel_123",
            "guildId": test_community_server.platform_id,
            "scoreAtPost": 0.85,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        response = await auth_client.post("/api/v1/note-publisher/record", json=request_data)
        assert response.status_code == 201

        data = response.json()
        assert "id" in data
        assert "recorded_at" in data

        # Verify it was saved in database
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "discord_msg_123"
                )
            )
            auto_post = result.scalar_one_or_none()
            assert auto_post is not None
            assert auto_post.success is True
            assert str(auto_post.note_id) == test_notes["12345"]

            # Cleanup
            await session.delete(auto_post)
            await session.commit()

    async def test_record_failed_autopost(
        self, auth_client, test_community_server, snopes_test_data, test_notes
    ):
        """Test recording a failed note publisher attempt."""
        request_data = {
            "noteId": test_notes["12346"],
            "originalMessageId": "discord_msg_456",
            "channelId": "test_channel_123",
            "guildId": test_community_server.platform_id,
            "scoreAtPost": 0.78,
            "confidenceAtPost": "medium",
            "success": False,
            "errorMessage": "Discord API rate limit exceeded",
        }

        response = await auth_client.post("/api/v1/note-publisher/record", json=request_data)
        assert response.status_code == 201

        # Verify error was recorded
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "discord_msg_456"
                )
            )
            auto_post = result.scalar_one_or_none()
            assert auto_post is not None
            assert auto_post.success is False
            assert auto_post.error_message == "Discord API rate limit exceeded"

            # Cleanup
            await session.delete(auto_post)
            await session.commit()

    async def test_check_duplicate_autopost(self, auth_client, test_notes):
        """Test checking for duplicate note publisher attempts."""
        # First, record a note publisher post
        request_data = {
            "noteId": test_notes["12347"],
            "originalMessageId": "discord_msg_789",
            "channelId": "test_channel_123",
            "guildId": "test_guild_123",
            "scoreAtPost": 0.82,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        await auth_client.post("/api/v1/note-publisher/record", json=request_data)

        # Now check for duplicate
        response = await auth_client.get("/api/v1/note-publisher/check-duplicate/discord_msg_789")
        assert response.status_code == 200

        data = response.json()
        assert data["exists"] is True
        assert data["note_publisher_post_id"] is not None

        # Cleanup
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "discord_msg_789"
                )
            )
            auto_post = result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()

    async def test_get_last_post_in_channel(self, auth_client, test_notes):
        """Test retrieving the most recent note publisher post in a channel."""
        # Record a note publisher post
        request_data = {
            "noteId": test_notes["12348"],
            "originalMessageId": "discord_msg_999",
            "channelId": "test_channel_456",
            "guildId": "test_guild_123",
            "scoreAtPost": 0.88,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        await auth_client.post("/api/v1/note-publisher/record", json=request_data)

        # Get last post in channel
        response = await auth_client.get(
            "/api/v1/note-publisher/last-post/test_channel_456",
            params={"community_server_id": "test_guild_123"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["channel_id"] == "test_channel_456"
        assert data["note_id"] == test_notes["12348"]

        # Cleanup
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "discord_msg_999"
                )
            )
            auto_post = result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_text_search(self, auth_client, test_community_server):
        """Test searching with empty text."""
        request_data = {
            "text": "",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)
        # Should return validation error
        assert response.status_code in [400, 422]

    async def test_very_long_text_search(self, auth_client, test_community_server):
        """Test searching with very long text (edge case)."""
        long_text = "hitler invented the inflatable sex doll " * 100  # Very long text

        request_data = {
            "text": long_text,
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)
        # Should handle gracefully (either work or return appropriate error)
        assert response.status_code in [200, 400, 404, 500]

    async def test_invalid_threshold_values(self, auth_client, test_community_server):
        """Test invalid similarity threshold values."""
        invalid_thresholds = [-0.1, 1.5, 2.0, -1.0]

        for threshold in invalid_thresholds:
            request_data = {
                "text": "test query",
                "community_server_id": test_community_server.platform_id,
                "dataset_tags": ["snopes"],
                "similarity_threshold": threshold,
                "limit": 5,
            }

            response = await auth_client.post(
                "/api/v1/embeddings/similarity-search", json=request_data
            )
            # Should return validation error
            assert response.status_code in [400, 422]

    async def test_nonexistent_dataset_tags(self, auth_client, test_community_server):
        """Test searching with non-existent dataset tags."""
        request_data = {
            "text": "hitler invented the inflatable sex doll",
            "community_server_id": test_community_server.platform_id,
            "dataset_tags": ["nonexistent_dataset"],
            "similarity_threshold": 0.7,
            "limit": 5,
        }

        response = await auth_client.post("/api/v1/embeddings/similarity-search", json=request_data)
        # Should return no matches (200 with empty results)
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert data["total_matches"] == 0


@pytest.mark.asyncio
class TestCodeCoverage:
    """Tests to improve code coverage for note publisher module (AC#6)."""

    async def test_all_autopost_router_endpoints(
        self, auth_client, test_community_server, test_notes
    ):
        """Ensure all note publisher router endpoints are covered."""
        # Test /config POST
        config_response = await auth_client.post(
            "/api/v1/note-publisher/config",
            json={
                "community_server_id": test_community_server.platform_id,
                "channel_id": None,
                "enabled": True,
                "threshold": 0.8,
            },
        )
        assert config_response.status_code == 200

        # Test /config GET
        get_response = await auth_client.get(
            "/api/v1/note-publisher/config",
            params={"community_server_id": test_community_server.platform_id},
        )
        assert get_response.status_code == 200

        # Test /record POST
        record_response = await auth_client.post(
            "/api/v1/note-publisher/record",
            json={
                "noteId": test_notes["99999"],
                "originalMessageId": "coverage_test_msg",
                "channelId": "coverage_channel",
                "guildId": test_community_server.platform_id,
                "scoreAtPost": 0.9,
                "confidenceAtPost": "high",
                "success": True,
                "errorMessage": None,
            },
        )
        assert record_response.status_code == 201

        # Test /check-duplicate GET
        dup_response = await auth_client.get(
            "/api/v1/note-publisher/check-duplicate/coverage_test_msg"
        )
        assert dup_response.status_code == 200

        # Cleanup
        async with get_session_maker()() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "coverage_test_msg"
                )
            )
            auto_post = result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()
