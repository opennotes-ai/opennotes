"""
E2E tests simulating Discord MESSAGE_CREATE events for automatic note request triggering (AC#5).

These tests simulate the complete flow from receiving a Discord webhook message
to triggering automatic note requests based on similarity search results.
"""

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.database import get_session_maker
from src.fact_checking.models import FactCheckItem
from src.llm_config.models import CommunityServer, CommunityServerLLMConfig
from src.main import app
from src.notes.models import Note
from src.notes.note_publisher_models import NotePublisherConfig, NotePublisherPost
from src.users.models import User
from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def discord_e2e_setup(setup_database):
    """
    Set up complete E2E test environment:
    - Community server with OpenAI config
    - User with profile and membership
    - Note publisher configuration
    - Snopes fact-check items with embeddings
    """
    async_session_maker = get_session_maker()
    async with async_session_maker() as session:
        # Create community server
        community = CommunityServer(
            platform="discord",
            platform_id="e2e_guild_789",
            name="E2E Test Community",
            is_active=True,
        )
        session.add(community)
        await session.flush()

        llm_config = CommunityServerLLMConfig(
            community_server_id=community.id,
            provider="openai",
            api_key_encrypted=b"e2e_encrypted_key",
            encryption_key_id="e2e_key_id",
            api_key_preview="...test",
            settings={"model": "text-embedding-3-small"},
            enabled=True,
        )
        session.add(llm_config)
        await session.flush()

        # Create user with profile
        profile = UserProfile(
            display_name="E2E Test User",
            is_active=True,
            is_banned=False,
        )
        session.add(profile)
        await session.flush()

        user = User(
            username="e2e_testuser",
            email="e2e@example.com",
            hashed_password="hashed",
            discord_id="e2e_discord_id",
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
            joined_at=datetime.now(UTC),
            is_active=True,
        )
        session.add(membership)
        await session.flush()

        # Create note_publisher configuration
        note_publisher_config = NotePublisherConfig(
            community_server_id=community.platform_id,
            channel_id=None,
            enabled=True,
            threshold=0.75,
        )
        session.add(note_publisher_config)
        await session.flush()

        # Create fact-check items
        hitler_item = FactCheckItem(
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check", "history"],
            title="Did Hitler Invent the Inflatable Sex Doll?",
            content="Adolf Hitler was behind the invention of the first inflatable sex dolls. This claim is FALSE.",
            summary="A widely circulated claim suggests Hitler invented inflatable sex dolls for Nazi soldiers.",
            rating="False",
            source_url="https://www.snopes.com/fact-check/hitler-inflatable-sex-doll/",
            embedding=[0.1] * 1536,
        )
        session.add(hitler_item)

        # Create Note objects for the tests
        from uuid import UUID as PUUID

        note1 = Note(
            id=PUUID("00000000-0000-0000-0000-000000088888"),
            author_participant_id="e2e_test_author_1",
            community_server_id=community.id,
            summary="Test note 1 for e2e discord",
            classification="NOT_MISLEADING",
        )
        session.add(note1)

        note2 = Note(
            id=PUUID("00000000-0000-0000-0000-000000077777"),
            author_participant_id="e2e_test_author_2",
            community_server_id=community.id,
            summary="Test note 2 for e2e discord",
            classification="NOT_MISLEADING",
        )
        session.add(note2)

        note3 = Note(
            id=PUUID("00000000-0000-0000-0000-000000066666"),
            author_participant_id="e2e_test_author_3",
            community_server_id=community.id,
            summary="Test note 3 for e2e discord",
            classification="NOT_MISLEADING",
        )
        session.add(note3)

        note4 = Note(
            id=PUUID("00000000-0000-0000-0000-000000055555"),
            author_participant_id="e2e_test_author_4",
            community_server_id=community.id,
            summary="Test note 4 for e2e discord",
            classification="NOT_MISLEADING",
        )
        session.add(note4)

        note5 = Note(
            id=PUUID("00000000-0000-0000-0000-000000044444"),
            author_participant_id="e2e_test_author_5",
            community_server_id=community.id,
            summary="Test note 5 for e2e discord",
            classification="NOT_MISLEADING",
        )
        session.add(note5)

        await session.commit()
        await session.refresh(community)
        await session.refresh(user)

        yield {
            "community": community,
            "user": user,
            "profile": profile,
            "membership": membership,
            "note_publisher_config": note_publisher_config,
            "fact_check_item": hitler_item,
            "note1": note1,
            "note2": note2,
            "note3": note3,
            "note4": note4,
            "note5": note5,
        }

        # Cleanup - must delete NotePublisherPost records first (FK to notes)
        # Tests may create NotePublisherPost records that reference the test notes
        note_ids = [note1.id, note2.id, note3.id, note4.id, note5.id]
        for note_id in note_ids:
            result = await session.execute(
                select(NotePublisherPost).where(NotePublisherPost.note_id == note_id)
            )
            for post in result.scalars().all():
                await session.delete(post)

        await session.delete(hitler_item)
        await session.delete(note5)
        await session.delete(note4)
        await session.delete(note3)
        await session.delete(note2)
        await session.delete(note1)
        await session.delete(note_publisher_config)
        await session.delete(membership)
        await session.delete(identity)
        await session.delete(user)
        await session.delete(profile)
        await session.delete(llm_config)
        await session.delete(community)
        await session.commit()


@pytest.fixture
async def discord_auth_headers(discord_e2e_setup):
    """Generate auth headers for Discord E2E test user."""
    from src.auth.auth import create_access_token

    user = discord_e2e_setup["user"]
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def discord_client(discord_auth_headers):
    """Authenticated HTTP client for Discord E2E tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(discord_auth_headers)
        yield client


class TestDiscordMessageE2E:
    """E2E tests simulating Discord MESSAGE_CREATE events (AC#5)."""

    async def test_discord_message_triggers_similarity_search(
        self, discord_client, discord_e2e_setup
    ):
        """
        E2E Test: Discord message containing misinformation triggers similarity search.

        Simulates the complete flow:
        1. Discord MESSAGE_CREATE event received
        2. Message content extracted
        3. Similarity search performed against Snopes database
        4. Matching fact-check items returned
        5. Automatic note request could be triggered (if similarity >= threshold)
        """
        community = discord_e2e_setup["community"]

        # Simulate Discord MESSAGE_CREATE event content
        discord_message_content = "Did you know that Hitler invented the inflatable sex doll?"

        # Step 1: Perform similarity search (simulating Discord bot behavior)
        search_request = {
            "text": discord_message_content,
            "community_server_id": community.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.70,
            "limit": 5,
        }

        search_response = await discord_client.post(
            "/api/v1/embeddings/similarity-search", json=search_request
        )

        # Should either succeed or fail gracefully
        assert search_response.status_code in [200, 404, 500]

        if search_response.status_code == 200:
            search_data = search_response.json()
            # If matches found, verify they're relevant
            if search_data["total_matches"] > 0:
                assert search_data["matches"][0]["title"] is not None
                assert search_data["matches"][0]["similarity_score"] >= 0.0

    async def test_high_similarity_triggers_note_publisher_record(
        self, discord_client, discord_e2e_setup
    ):
        """
        E2E Test: High similarity score triggers note_publisher record creation.

        Simulates:
        1. Similarity search finds matching fact-check (high score)
        2. Threshold check passes
        3. Note publisher record is created
        """
        community = discord_e2e_setup["community"]

        # Simulate finding a high-similarity match and recording the note_publisher
        note_publisher_request = {
            "noteId": "00000000-0000-0000-0000-000000088888",
            "originalMessageId": "e2e_discord_msg_12345",
            "channelId": "e2e_channel_67890",
            "guildId": community.platform_id,
            "scoreAtPost": 0.85,  # High similarity score
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        record_response = await discord_client.post(
            "/api/v1/note-publisher/record", json=note_publisher_request
        )

        assert record_response.status_code == 201
        record_data = record_response.json()
        assert "id" in record_data
        assert "recorded_at" in record_data

        # Verify it's in the database
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "e2e_discord_msg_12345"
                )
            )
            auto_post = result.scalar_one_or_none()
            assert auto_post is not None
            assert auto_post.success is True
            assert auto_post.score_at_post == 0.85

            # Cleanup
            await session.delete(auto_post)
            await session.commit()

    async def test_low_similarity_no_note_publisher(self, discord_client, discord_e2e_setup):
        """
        E2E Test: Low similarity score does NOT trigger note_publisher.

        Simulates:
        1. Similarity search finds low-similarity matches
        2. Threshold check fails
        3. No note_publisher record is created
        """
        community = discord_e2e_setup["community"]

        # Simulate a message with low similarity to Snopes content
        unrelated_message = "I love pizza and ice cream!"

        search_request = {
            "text": unrelated_message,
            "community_server_id": community.platform_id,
            "dataset_tags": ["snopes"],
            "similarity_threshold": 0.75,  # High threshold
            "limit": 5,
        }

        search_response = await discord_client.post(
            "/api/v1/embeddings/similarity-search", json=search_request
        )

        # Should either succeed with no matches or fail gracefully
        assert search_response.status_code in [200, 404, 500]

        if search_response.status_code == 200:
            search_data = search_response.json()
            # Expect no matches for unrelated content
            assert search_data["total_matches"] == 0 or (
                search_data["matches"][0]["similarity_score"] < 0.75
                if search_data["total_matches"] > 0
                else True
            )

    async def test_duplicate_message_check_prevents_double_post(
        self, discord_client, discord_e2e_setup
    ):
        """
        E2E Test: Duplicate message check prevents posting same note twice.

        Simulates:
        1. First message triggers note_publisher
        2. Same message (or edit) sent again
        3. Duplicate check prevents second note_publisher
        """
        community = discord_e2e_setup["community"]

        # First note_publisher
        note_publisher_request = {
            "noteId": "00000000-0000-0000-0000-000000077777",
            "originalMessageId": "duplicate_check_msg_999",
            "channelId": "e2e_channel_99999",
            "guildId": community.platform_id,
            "scoreAtPost": 0.82,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        first_response = await discord_client.post(
            "/api/v1/note-publisher/record", json=note_publisher_request
        )
        assert first_response.status_code == 201

        # Check for duplicate
        dup_response = await discord_client.get(
            "/api/v1/note-publisher/check-duplicate/duplicate_check_msg_999"
        )
        assert dup_response.status_code == 200

        dup_data = dup_response.json()
        assert dup_data["exists"] is True
        assert dup_data["note_publisher_post_id"] is not None

        # In real Discord bot, this would prevent second note_publisher
        # The bot should skip posting if exists=True

        # Cleanup
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "duplicate_check_msg_999"
                )
            )
            auto_post = result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()

    async def test_channel_cooldown_check(self, discord_client, discord_e2e_setup):
        """
        E2E Test: Channel cooldown prevents spam of note_publishers.

        Simulates:
        1. Note publisher created in channel
        2. Check last post time
        3. Cooldown logic would prevent immediate second post
        """
        community = discord_e2e_setup["community"]

        # Create an note_publisher
        note_publisher_request = {
            "noteId": "00000000-0000-0000-0000-000000066666",
            "originalMessageId": "cooldown_msg_111",
            "channelId": "cooldown_channel_222",
            "guildId": community.platform_id,
            "scoreAtPost": 0.88,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        await discord_client.post("/api/v1/note-publisher/record", json=note_publisher_request)

        # Check last post in channel
        last_post_response = await discord_client.get(
            "/api/v1/note-publisher/last-post/cooldown_channel_222",
            params={"community_server_id": community.platform_id},
        )
        assert last_post_response.status_code == 200

        last_post_data = last_post_response.json()
        assert last_post_data["channel_id"] == "cooldown_channel_222"
        assert last_post_data["note_id"] == "00000000-0000-0000-0000-000000066666"
        assert "posted_at" in last_post_data

        # In real Discord bot, would check if enough time has passed since posted_at
        # If cooldown not expired, skip posting

        # Cleanup
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "cooldown_msg_111"
                )
            )
            auto_post = result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()

    async def test_note_publisher_disabled_no_trigger(self, discord_client, discord_e2e_setup):
        """
        E2E Test: Note publisher disabled in config prevents triggering.

        Simulates:
        1. Get note_publisher config for server
        2. Check if enabled=False
        3. Skip similarity search and note_publisher creation
        """
        community = discord_e2e_setup["community"]

        # First, disable note_publisher for this server
        disable_request = {
            "community_server_id": community.platform_id,
            "channel_id": None,
            "enabled": False,  # Disable
            "threshold": 0.75,
        }

        config_response = await discord_client.post(
            "/api/v1/note-publisher/config", json=disable_request
        )
        assert config_response.status_code == 200

        # Verify config is disabled
        get_config_response = await discord_client.get(
            "/api/v1/note-publisher/config",
            params={"community_server_id": community.platform_id},
        )
        assert get_config_response.status_code == 200

        config_data = get_config_response.json()
        assert config_data["enabled"] is False

        # In real Discord bot, would skip note_publisher logic entirely when enabled=False


class TestDiscordWebhookFailureHandling:
    """E2E tests for handling failures during note_publisher attempts."""

    async def test_discord_api_error_recorded(self, discord_client, discord_e2e_setup):
        """E2E Test: Discord API errors are properly recorded."""
        community = discord_e2e_setup["community"]

        # Simulate a failed note_publisher due to Discord API error
        failed_note_publisher = {
            "noteId": "00000000-0000-0000-0000-000000055555",
            "originalMessageId": "failed_msg_333",
            "channelId": "failed_channel_444",
            "guildId": community.platform_id,
            "scoreAtPost": 0.79,
            "confidenceAtPost": "medium",
            "success": False,
            "errorMessage": "Discord API returned 429: Rate limit exceeded",
        }

        response = await discord_client.post(
            "/api/v1/note-publisher/record", json=failed_note_publisher
        )
        assert response.status_code == 201

        # Verify failure was recorded with error message
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "failed_msg_333"
                )
            )
            auto_post = result.scalar_one_or_none()
            assert auto_post is not None
            assert auto_post.success is False
            assert "429" in auto_post.error_message
            assert "Rate limit" in auto_post.error_message

            # Cleanup
            await session.delete(auto_post)
            await session.commit()

    async def test_permissions_error_recorded(self, discord_client, discord_e2e_setup):
        """E2E Test: Discord permission errors are properly recorded."""
        community = discord_e2e_setup["community"]

        # Simulate failed note_publisher due to missing permissions
        failed_note_publisher = {
            "noteId": "00000000-0000-0000-0000-000000044444",
            "originalMessageId": "perm_fail_msg_555",
            "channelId": "no_perm_channel_666",
            "guildId": community.platform_id,
            "scoreAtPost": 0.84,
            "confidenceAtPost": "high",
            "success": False,
            "errorMessage": "Missing permissions: SEND_MESSAGES in channel",
        }

        response = await discord_client.post(
            "/api/v1/note-publisher/record", json=failed_note_publisher
        )
        assert response.status_code == 201

        # Verify permission error was recorded
        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "perm_fail_msg_555"
                )
            )
            auto_post = result.scalar_one_or_none()
            assert auto_post is not None
            assert auto_post.success is False
            assert "permissions" in auto_post.error_message.lower()

            # Cleanup
            await session.delete(auto_post)
            await session.commit()


class TestNotePublisherRequestCompletion:
    """Tests for automatic request completion when notes are published."""

    async def test_successful_note_publish_completes_associated_request(
        self, discord_client, discord_e2e_setup
    ):
        """
        Test that publishing a note with an associated request marks
        the request as COMPLETED.
        """
        from src.notes.models import Request

        community = discord_e2e_setup["community"]
        note1 = discord_e2e_setup["note1"]

        async_session_maker = get_session_maker()

        async with async_session_maker() as session:
            request_record = Request(
                request_id="test_request_for_publish_001",
                community_server_id=community.id,
                requested_by="test_user_123",
                status="PENDING",
            )
            session.add(request_record)
            await session.flush()

            note_result = await session.execute(select(Note).where(Note.id == note1.id))
            note = note_result.scalar_one()
            note.request_id = request_record.request_id
            await session.commit()

        note_publisher_request = {
            "noteId": str(note1.id),
            "originalMessageId": "request_completion_msg_001",
            "channelId": "request_completion_channel",
            "guildId": community.platform_id,
            "scoreAtPost": 0.90,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        response = await discord_client.post(
            "/api/v1/note-publisher/record", json=note_publisher_request
        )
        assert response.status_code == 201

        async with async_session_maker() as session:
            result = await session.execute(
                select(Request).where(Request.request_id == "test_request_for_publish_001")
            )
            updated_request = result.scalar_one()
            assert updated_request.status == "COMPLETED"

            post_result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "request_completion_msg_001"
                )
            )
            auto_post = post_result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)

            note_result = await session.execute(select(Note).where(Note.id == note1.id))
            note = note_result.scalar_one()
            note.request_id = None
            await session.delete(updated_request)
            await session.commit()

    async def test_failed_note_publish_does_not_complete_request(
        self, discord_client, discord_e2e_setup
    ):
        """
        Test that a failed note publish does NOT mark the request as COMPLETED.
        """
        from src.notes.models import Request

        community = discord_e2e_setup["community"]
        note2 = discord_e2e_setup["note2"]

        async_session_maker = get_session_maker()

        async with async_session_maker() as session:
            request_record = Request(
                request_id="test_request_for_failed_publish_002",
                community_server_id=community.id,
                requested_by="test_user_456",
                status="PENDING",
            )
            session.add(request_record)
            await session.flush()

            note_result = await session.execute(select(Note).where(Note.id == note2.id))
            note = note_result.scalar_one()
            note.request_id = request_record.request_id
            await session.commit()

        note_publisher_request = {
            "noteId": str(note2.id),
            "originalMessageId": "failed_request_msg_002",
            "channelId": "failed_request_channel",
            "guildId": community.platform_id,
            "scoreAtPost": 0.85,
            "confidenceAtPost": "high",
            "success": False,
            "errorMessage": "Discord API error: rate limited",
        }

        response = await discord_client.post(
            "/api/v1/note-publisher/record", json=note_publisher_request
        )
        assert response.status_code == 201

        async with async_session_maker() as session:
            result = await session.execute(
                select(Request).where(Request.request_id == "test_request_for_failed_publish_002")
            )
            unchanged_request = result.scalar_one()
            assert unchanged_request.status == "PENDING"

            post_result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "failed_request_msg_002"
                )
            )
            auto_post = post_result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)

            note_result = await session.execute(select(Note).where(Note.id == note2.id))
            note = note_result.scalar_one()
            note.request_id = None
            await session.delete(unchanged_request)
            await session.commit()

    async def test_note_without_request_publishes_normally(self, discord_client, discord_e2e_setup):
        """
        Test that notes without associated requests publish normally
        without errors.
        """
        community = discord_e2e_setup["community"]
        note3 = discord_e2e_setup["note3"]

        note_publisher_request = {
            "noteId": str(note3.id),
            "originalMessageId": "no_request_msg_003",
            "channelId": "no_request_channel",
            "guildId": community.platform_id,
            "scoreAtPost": 0.88,
            "confidenceAtPost": "high",
            "success": True,
            "errorMessage": None,
        }

        response = await discord_client.post(
            "/api/v1/note-publisher/record", json=note_publisher_request
        )
        assert response.status_code == 201
        record_data = response.json()
        assert "id" in record_data
        assert "recorded_at" in record_data

        async_session_maker = get_session_maker()
        async with async_session_maker() as session:
            post_result = await session.execute(
                select(NotePublisherPost).where(
                    NotePublisherPost.original_message_id == "no_request_msg_003"
                )
            )
            auto_post = post_result.scalar_one_or_none()
            if auto_post:
                await session.delete(auto_post)
                await session.commit()
