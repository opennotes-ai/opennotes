"""
Integration tests for AI note generation from bulk scan note-requests endpoint.

These tests verify that:
1. When generate_ai_notes=True, REQUEST_AUTO_CREATED events are published for flagged messages
2. Similarity matches (with fact_check_item_id) trigger events correctly
3. OpenAI moderation matches trigger events (schema needs modification for this)
4. When generate_ai_notes=False, NO events are published

Task: task-941

TDD RED PHASE: These tests are expected to FAIL until the implementation is fixed.

Identified Bugs (discovered via TDD):
1. Bug #1 (service.py line 1063): community_server_id is passed as platform_id (e.g., "discord_guild_id")
   instead of the actual UUID of the CommunityServer. The code queries for platform_id and
   passes that to the event, but the event schema expects the UUID.
   FIX: Change line 1063 from `community_server_id=platform_id` to `community_server_id=str(community_server_id)`

2. Bug #2 (service.py line 1059-1071): Events are published even when fact_check_item_id is None.
   For similarity scans, if a match doesn't have a fact_check_item_id (legacy scans), we should
   NOT publish an event since the AI note generation handler requires a fact_check_item.
   FIX: Add condition `and first_match.fact_check_item_id` to the `if` statement on line 1059
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.auth.auth import create_access_token
from src.bulk_content_scan.schemas import FlaggedMessage, OpenAIModerationMatch, SimilarityMatch
from src.main import app


class TestBulkScanAINoteGenerationFixtures:
    """Fixtures for bulk scan AI note generation tests."""

    @pytest.fixture
    async def community_server_for_ai_tests(self, db):
        """Create a community server for AI note generation tests."""
        from src.llm_config.models import CommunityServer

        server = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id="ai_note_test_community",
            name="AI Note Generation Test Community",
            is_active=True,
            is_public=True,
        )
        db.add(server)
        await db.commit()
        await db.refresh(server)
        return server

    @pytest.fixture
    async def fact_check_item_for_tests(self, db):
        """Create a fact check item for similarity match tests."""
        from src.fact_checking.models import FactCheckItem

        item = FactCheckItem(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check"],
            title="Test Fact Check Claim",
            content="This is a test fact-check item for bulk scan AI note generation tests.",
            source_url="https://example.com/fact-check",
            rating="False",
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @pytest.fixture
    async def admin_user_for_ai_tests(self, db, community_server_for_ai_tests):
        """Create an admin user for the test community."""
        from src.users.models import User
        from src.users.profile_crud import create_community_member, create_profile_with_identity
        from src.users.profile_schemas import (
            AuthProvider,
            CommunityMemberCreate,
            CommunityRole,
            UserProfileCreate,
        )

        user = User(
            id=uuid4(),
            username="ai_note_test_admin",
            email="ai_note_admin@test.local",
            hashed_password="hashed_password_placeholder",
            role="user",
            is_active=True,
            is_superuser=False,
            discord_id="discord_ai_note_admin",
        )
        db.add(user)
        await db.flush()

        profile_create = UserProfileCreate(
            display_name="AI Note Test Admin",
            avatar_url=None,
            bio="Admin user for AI note generation tests",
            role="user",
            is_opennotes_admin=False,
            is_human=True,
            is_active=True,
            is_banned=False,
            banned_at=None,
            banned_reason=None,
        )

        profile, identity = await create_profile_with_identity(
            db=db,
            profile_create=profile_create,
            provider=AuthProvider.DISCORD,
            provider_user_id=user.discord_id,
            credentials=None,
        )

        member_create = CommunityMemberCreate(
            community_id=community_server_for_ai_tests.id,
            profile_id=profile.id,
            is_external=False,
            role=CommunityRole.ADMIN,
            permissions=None,
            joined_at=datetime.now(UTC),
            invited_by=None,
            invitation_reason="Admin fixture for AI note generation tests",
        )
        await create_community_member(db, member_create)

        await db.commit()
        await db.refresh(user)

        return {
            "user": user,
            "profile": profile,
            "identity": identity,
            "community": community_server_for_ai_tests,
        }

    @pytest.fixture
    def admin_headers_for_ai_tests(self, admin_user_for_ai_tests):
        """Auth headers for admin user."""
        user = admin_user_for_ai_tests["user"]
        token_data = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
        }
        access_token = create_access_token(token_data)
        return {"Authorization": f"Bearer {access_token}"}

    @pytest.fixture
    async def completed_scan_with_similarity_matches(
        self, db, community_server_for_ai_tests, admin_user_for_ai_tests, fact_check_item_for_tests
    ):
        """Create a completed scan with flagged messages that have similarity matches."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server_for_ai_tests.id,
            initiated_by_user_id=admin_user_for_ai_tests["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=100,
            messages_flagged=2,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)

        flagged_messages = [
            FlaggedMessage(
                message_id=f"sim_msg_{i}",
                channel_id="test_channel_123",
                content=f"Test message content {i} that matched a fact check",
                author_id=f"author_{i}",
                timestamp=datetime.now(UTC),
                matches=[
                    SimilarityMatch(
                        scan_type="similarity",
                        score=0.85 + (i * 0.05),
                        matched_claim="Test claim that was matched",
                        matched_source="https://example.com/source",
                        fact_check_item_id=fact_check_item_for_tests.id,
                    )
                ],
            )
            for i in range(2)
        ]

        return {
            "scan": scan,
            "flagged_messages": flagged_messages,
            "fact_check_item": fact_check_item_for_tests,
            "community_server": community_server_for_ai_tests,
        }

    @pytest.fixture
    async def completed_scan_with_moderation_matches(
        self, db, community_server_for_ai_tests, admin_user_for_ai_tests
    ):
        """Create a completed scan with flagged messages that have OpenAI moderation matches."""
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server_for_ai_tests.id,
            initiated_by_user_id=admin_user_for_ai_tests["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=50,
            messages_flagged=1,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)

        flagged_messages = [
            FlaggedMessage(
                message_id="mod_msg_1",
                channel_id="test_channel_456",
                content="Test message content that was flagged by moderation",
                author_id="author_mod_1",
                timestamp=datetime.now(UTC),
                matches=[
                    OpenAIModerationMatch(
                        scan_type="openai_moderation",
                        max_score=0.92,
                        categories={"harassment": True, "violence": False},
                        scores={"harassment": 0.92, "violence": 0.1},
                        flagged_categories=["harassment"],
                    )
                ],
            )
        ]

        return {
            "scan": scan,
            "flagged_messages": flagged_messages,
        }


class TestSimilarityMatchAINoteGeneration(TestBulkScanAINoteGenerationFixtures):
    """
    Tests for AI note generation from similarity-matched flagged messages.

    These tests verify that when generate_ai_notes=True and flagged messages
    have similarity matches (with fact_check_item_id), REQUEST_AUTO_CREATED
    events are published for each message.
    """

    @pytest.mark.asyncio
    async def test_similarity_match_publishes_request_auto_created_event(
        self,
        db,
        admin_headers_for_ai_tests,
        completed_scan_with_similarity_matches,
    ):
        """
        TDD RED: Similarity match with generate_ai_notes=True should publish REQUEST_AUTO_CREATED events.

        Expected behavior:
        - For each message_id in the request, if it has a similarity match with fact_check_item_id,
          a REQUEST_AUTO_CREATED event should be published
        - The event should contain: request_id, platform_message_id, fact_check_item_id,
          community_server_id, content, similarity_score, dataset_name

        Current bug: create_note_requests_from_flagged_messages() never publishes events.
        """
        scan_data = completed_scan_with_similarity_matches
        scan = scan_data["scan"]
        flagged_messages = scan_data["flagged_messages"]
        fact_check_item = scan_data["fact_check_item"]
        community_server = scan_data["community_server"]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            with patch(
                "src.events.publisher.event_publisher.publish_request_auto_created"
            ) as mock_publish:
                mock_publish.return_value = "test_event_id"

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v2/bulk-scans/{scan.id}/note-requests",
                        headers={
                            **admin_headers_for_ai_tests,
                            "Content-Type": "application/vnd.api+json",
                        },
                        json={
                            "data": {
                                "type": "note-requests",
                                "attributes": {
                                    "message_ids": ["sim_msg_0", "sim_msg_1"],
                                    "generate_ai_notes": True,
                                },
                            }
                        },
                    )

                assert response.status_code == 201, (
                    f"Expected 201 Created but got {response.status_code}. "
                    f"Response: {response.text}"
                )

                assert mock_publish.call_count == 2, (
                    f"Expected 2 calls to publish_request_auto_created but got {mock_publish.call_count}. "
                    "Bug: REQUEST_AUTO_CREATED events are not being published when generate_ai_notes=True."
                )

                for call_args in mock_publish.call_args_list:
                    kwargs = call_args.kwargs if call_args.kwargs else {}

                    if kwargs:
                        assert "request_id" in kwargs
                        assert kwargs["scan_type"] == "similarity"
                        assert kwargs["fact_check_item_id"] == str(fact_check_item.id)
                        assert (
                            kwargs["community_server_id"]
                            == community_server.platform_community_server_id
                        )
                        assert kwargs["similarity_score"] >= 0.85

    @pytest.mark.asyncio
    async def test_similarity_match_event_contains_correct_data(
        self,
        db,
        admin_headers_for_ai_tests,
        completed_scan_with_similarity_matches,
    ):
        """
        TDD RED: Verify REQUEST_AUTO_CREATED event contains all required fields.

        The event schema requires:
        - request_id: str (the created request's ID)
        - platform_message_id: str | None (Discord message ID)
        - fact_check_item_id: str (UUID of matched fact-check item)
        - community_server_id: str (community server identifier)
        - content: str (message content)
        - similarity_score: float (match score)
        - dataset_name: str (always "bulk_scan" for this flow)
        """
        scan_data = completed_scan_with_similarity_matches
        scan = scan_data["scan"]
        flagged_messages = scan_data["flagged_messages"]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            with patch(
                "src.events.publisher.event_publisher.publish_request_auto_created"
            ) as mock_publish:
                mock_publish.return_value = "test_event_id"

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v2/bulk-scans/{scan.id}/note-requests",
                        headers={
                            **admin_headers_for_ai_tests,
                            "Content-Type": "application/vnd.api+json",
                        },
                        json={
                            "data": {
                                "type": "note-requests",
                                "attributes": {
                                    "message_ids": ["sim_msg_0"],
                                    "generate_ai_notes": True,
                                },
                            }
                        },
                    )

                assert response.status_code == 201

                mock_publish.assert_called_once()
                call_kwargs = mock_publish.call_args.kwargs

                assert "request_id" in call_kwargs, "Event missing request_id"
                assert "platform_message_id" in call_kwargs, "Event missing platform_message_id"
                assert call_kwargs["platform_message_id"] == "sim_msg_0"
                assert "scan_type" in call_kwargs, "Event missing scan_type"
                assert call_kwargs["scan_type"] == "similarity"
                assert "fact_check_item_id" in call_kwargs, "Event missing fact_check_item_id"
                assert "community_server_id" in call_kwargs, "Event missing community_server_id"
                assert "content" in call_kwargs, "Event missing content"
                assert "similarity_score" in call_kwargs, "Event missing similarity_score"


class TestModerationMatchAINoteGeneration(TestBulkScanAINoteGenerationFixtures):
    """
    Tests for AI note generation from OpenAI moderation-matched flagged messages.

    Note: The current RequestAutoCreatedEvent schema requires fact_check_item_id,
    but moderation matches don't have a fact-check item. The schema will need to be
    extended to support moderation scans:
    - scan_type: Literal["similarity", "openai_moderation"]
    - fact_check_item_id: str | None (optional, only for similarity)
    - moderation_metadata: dict | None (for moderation scans)
    """

    @pytest.mark.asyncio
    async def test_moderation_match_publishes_event_without_fact_check_item(
        self,
        db,
        admin_headers_for_ai_tests,
        completed_scan_with_moderation_matches,
        community_server_for_ai_tests,
    ):
        """
        Moderation match should publish event even without fact_check_item_id.

        The schema now supports moderation scans with:
        - scan_type set to "openai_moderation"
        - fact_check_item_id = None
        - moderation_metadata contains category/score information
        """
        scan_data = completed_scan_with_moderation_matches
        scan = scan_data["scan"]
        flagged_messages = scan_data["flagged_messages"]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            with patch(
                "src.events.publisher.event_publisher.publish_request_auto_created"
            ) as mock_publish:
                mock_publish.return_value = "test_event_id"

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v2/bulk-scans/{scan.id}/note-requests",
                        headers={
                            **admin_headers_for_ai_tests,
                            "Content-Type": "application/vnd.api+json",
                        },
                        json={
                            "data": {
                                "type": "note-requests",
                                "attributes": {
                                    "message_ids": ["mod_msg_1"],
                                    "generate_ai_notes": True,
                                },
                            }
                        },
                    )

                assert response.status_code == 201
                mock_publish.assert_called_once()

                call_kwargs = mock_publish.call_args.kwargs
                assert call_kwargs["scan_type"] == "openai_moderation"
                assert call_kwargs.get("fact_check_item_id") is None
                assert "moderation_metadata" in call_kwargs
                assert call_kwargs["moderation_metadata"]["flagged_categories"] == ["harassment"]


class TestGenerateAINotesDisabled(TestBulkScanAINoteGenerationFixtures):
    """
    Tests verifying that NO events are published when generate_ai_notes=False.

    This is the expected behavior - the flag should control whether AI note
    generation is triggered via events.
    """

    @pytest.mark.asyncio
    async def test_no_events_published_when_generate_ai_notes_is_false(
        self,
        db,
        admin_headers_for_ai_tests,
        completed_scan_with_similarity_matches,
    ):
        """
        Verify no REQUEST_AUTO_CREATED events when generate_ai_notes=False.

        This test should pass even with the current buggy implementation
        because no events are published regardless of the flag value.
        However, it's included to ensure we don't accidentally publish events
        when the flag is False after fixing the bug.
        """
        scan_data = completed_scan_with_similarity_matches
        scan = scan_data["scan"]
        flagged_messages = scan_data["flagged_messages"]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            with patch(
                "src.events.publisher.event_publisher.publish_request_auto_created"
            ) as mock_publish:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v2/bulk-scans/{scan.id}/note-requests",
                        headers={
                            **admin_headers_for_ai_tests,
                            "Content-Type": "application/vnd.api+json",
                        },
                        json={
                            "data": {
                                "type": "note-requests",
                                "attributes": {
                                    "message_ids": ["sim_msg_0", "sim_msg_1"],
                                    "generate_ai_notes": False,
                                },
                            }
                        },
                    )

                assert response.status_code == 201, (
                    f"Expected 201 Created but got {response.status_code}. "
                    f"Response: {response.text}"
                )

                assert mock_publish.call_count == 0, (
                    f"Expected 0 calls when generate_ai_notes=False but got {mock_publish.call_count}. "
                    "Events should only be published when generate_ai_notes=True."
                )

    @pytest.mark.asyncio
    async def test_note_requests_created_regardless_of_ai_flag(
        self,
        db,
        admin_headers_for_ai_tests,
        completed_scan_with_similarity_matches,
    ):
        """
        Note requests should be created in database regardless of generate_ai_notes flag.

        The generate_ai_notes flag only controls event publishing, not request creation.
        """

        scan_data = completed_scan_with_similarity_matches
        scan = scan_data["scan"]
        flagged_messages = scan_data["flagged_messages"]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    f"/api/v2/bulk-scans/{scan.id}/note-requests",
                    headers={
                        **admin_headers_for_ai_tests,
                        "Content-Type": "application/vnd.api+json",
                    },
                    json={
                        "data": {
                            "type": "note-requests",
                            "attributes": {
                                "message_ids": ["sim_msg_0"],
                                "generate_ai_notes": False,
                            },
                        }
                    },
                )

            assert response.status_code == 201

            response_data = response.json()
            created_count = response_data["data"]["attributes"]["created_count"]
            assert created_count == 1, "One note request should be created"


class TestPartialMatches(TestBulkScanAINoteGenerationFixtures):
    """
    Tests for edge cases with partial or mixed matches.
    """

    @pytest.fixture
    async def fact_check_item_for_partial_tests(self, db):
        """Create a fact check item for partial match tests."""
        from src.fact_checking.models import FactCheckItem

        item = FactCheckItem(
            id=uuid4(),
            dataset_name="snopes",
            dataset_tags=["snopes", "fact-check"],
            title="Test Fact Check for Partial Matches",
            content="This is a test fact-check item for partial match tests.",
            source_url="https://example.com/fact-check-partial",
            rating="Mostly False",
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        return item

    @pytest.mark.asyncio
    async def test_only_similarity_matches_with_fact_check_item_trigger_events(
        self,
        db,
        admin_headers_for_ai_tests,
        community_server_for_ai_tests,
        admin_user_for_ai_tests,
        fact_check_item_for_partial_tests,
    ):
        """
        Only similarity matches WITH fact_check_item_id should trigger events.

        Matches with fact_check_item_id trigger REQUEST_AUTO_CREATED events.
        Matches without fact_check_item_id (legacy scans) do NOT trigger events
        because the AI note generation handler requires a fact_check_item.
        """
        from src.bulk_content_scan.models import BulkContentScanLog

        scan = BulkContentScanLog(
            id=uuid4(),
            community_server_id=community_server_for_ai_tests.id,
            initiated_by_user_id=admin_user_for_ai_tests["profile"].id,
            scan_window_days=7,
            status="completed",
            initiated_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            messages_scanned=50,
            messages_flagged=2,
        )
        db.add(scan)
        await db.commit()
        await db.refresh(scan)

        flagged_messages = [
            FlaggedMessage(
                message_id="msg_with_fact_check",
                channel_id="test_channel",
                content="Message with fact check item",
                author_id="author_1",
                timestamp=datetime.now(UTC),
                matches=[
                    SimilarityMatch(
                        scan_type="similarity",
                        score=0.90,
                        matched_claim="Claim",
                        matched_source="https://example.com",
                        fact_check_item_id=fact_check_item_for_partial_tests.id,
                    )
                ],
            ),
            FlaggedMessage(
                message_id="msg_without_fact_check",
                channel_id="test_channel",
                content="Message without fact check item (legacy scan)",
                author_id="author_2",
                timestamp=datetime.now(UTC),
                matches=[
                    SimilarityMatch(
                        scan_type="similarity",
                        score=0.88,
                        matched_claim="Another claim",
                        matched_source="https://example.com/other",
                        fact_check_item_id=None,
                    )
                ],
            ),
        ]

        with patch(
            "src.bulk_content_scan.service.BulkContentScanService.get_flagged_results"
        ) as mock_get_flagged:
            mock_get_flagged.return_value = flagged_messages

            with patch(
                "src.events.publisher.event_publisher.publish_request_auto_created"
            ) as mock_publish:
                mock_publish.return_value = "test_event_id"

                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v2/bulk-scans/{scan.id}/note-requests",
                        headers={
                            **admin_headers_for_ai_tests,
                            "Content-Type": "application/vnd.api+json",
                        },
                        json={
                            "data": {
                                "type": "note-requests",
                                "attributes": {
                                    "message_ids": [
                                        "msg_with_fact_check",
                                        "msg_without_fact_check",
                                    ],
                                    "generate_ai_notes": True,
                                },
                            }
                        },
                    )

                assert response.status_code == 201

                assert mock_publish.call_count == 1, (
                    f"Expected 1 call (only message with fact_check_item_id triggers event) "
                    f"but got {mock_publish.call_count}"
                )

                call_kwargs = mock_publish.call_args.kwargs
                assert call_kwargs["platform_message_id"] == "msg_with_fact_check"
                assert call_kwargs["fact_check_item_id"] == str(
                    fact_check_item_for_partial_tests.id
                )
