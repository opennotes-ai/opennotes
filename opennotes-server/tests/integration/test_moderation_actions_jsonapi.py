"""Integration tests for JSON:API v2 moderation-actions endpoints.

Tests cover:
- POST / creates action in PROPOSED state and returns 201 with JSON:API shape
- GET /{action_id} returns action with classifier_evidence
- GET / with filters returns filtered results
- PATCH /{action_id} valid transition returns 200 and publishes event
- PATCH /{action_id} invalid transition returns 422
- Auth required (401 without token)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.moderation_actions.models import ActionState, ActionTier, ActionType, ReviewGroup


@pytest.fixture(autouse=True)
async def ensure_app_started():
    """Set app.state.startup_complete to True so StartupGateMiddleware lets requests through.

    ASGITransport does not run the app lifespan, so startup_complete is never set
    by the background init task. Without this fixture every request returns 503.
    """
    app.state.startup_complete = True


@pytest.fixture
async def modaction_community_server():
    """Create a test community server for moderation action tests."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = f"test_guild_modaction_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for Moderation Actions",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def modaction_registered_user(modaction_community_server):
    """Register a community admin user for moderation action tests."""
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    username = f"modactionuser_{uuid4().hex[:8]}"
    test_user = {
        "username": username,
        "email": f"{username}@example.com",
        "password": "TestPassword123!",
        "full_name": "Mod Action Test User",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/register", json=test_user)
        assert resp.status_code in (200, 201), f"Register failed: {resp.text}"

    async with get_session_maker()() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one()

        user.discord_id = f"modaction_discord_{uuid4().hex[:8]}"

        profile = UserProfile(
            display_name=user.full_name or user.username,
            is_human=True,
            is_active=True,
        )
        session.add(profile)
        await session.flush()

        identity = UserIdentity(
            profile_id=profile.id,
            provider="discord",
            provider_user_id=user.discord_id,
        )
        session.add(identity)

        member = CommunityMember(
            community_id=modaction_community_server["uuid"],
            profile_id=profile.id,
            role="admin",
            is_active=True,
            joined_at=datetime.now(UTC),
        )
        session.add(member)

        await session.commit()
        await session.refresh(user)
        await session.refresh(profile)

        return {
            "id": user.id,
            "username": user.username,
            "profile_id": profile.id,
        }


@pytest.fixture
async def modaction_auth_headers(modaction_registered_user):
    """Generate auth headers for the moderation action test user."""
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(modaction_registered_user["id"]),
        "username": modaction_registered_user["username"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def modaction_auth_client(modaction_auth_headers):
    """Authenticated HTTP client for moderation action tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(modaction_auth_headers)
        yield client


@pytest.fixture
async def modaction_request(modaction_community_server):
    """Create a Request row that ModerationAction can reference via FK."""
    from src.database import get_session_maker
    from src.notes.models import Request

    async with get_session_maker()() as db:
        req = Request(
            request_id=f"modaction_req_{uuid4().hex[:8]}",
            community_server_id=modaction_community_server["uuid"],
            requested_by="test_discord_user",
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)
        return {"id": req.id}


def _build_create_body(community_server_id, request_id):
    return {
        "request_id": str(request_id),
        "community_server_id": str(community_server_id),
        "action_type": ActionType.HIDE.value,
        "action_tier": ActionTier.TIER_1_IMMEDIATE.value,
        "review_group": ReviewGroup.COMMUNITY.value,
        "classifier_evidence": {
            "labels": ["hate_speech"],
            "scores": [0.95],
        },
    }


class TestModerationActionsPost:
    """POST /api/v2/moderation-actions"""

    @pytest.mark.asyncio
    async def test_create_returns_201_with_jsonapi_shape(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        assert response.status_code == 201, response.text
        data = response.json()

        assert "data" in data
        assert "jsonapi" in data
        assert data["jsonapi"]["version"] == "1.1"

        resource = data["data"]
        assert resource["type"] == "moderation-actions"
        assert "id" in resource
        assert isinstance(resource["id"], str)

        attrs = resource["attributes"]
        assert attrs["action_state"] == ActionState.PROPOSED.value
        assert attrs["action_type"] == ActionType.HIDE.value
        assert "classifier_evidence" in attrs
        assert attrs["classifier_evidence"]["labels"] == ["hate_speech"]

    @pytest.mark.asyncio
    async def test_create_publishes_proposed_event(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        assert response.status_code == 201, response.text
        assert mock_pub.called, "Expected publish_event to be called"
        event_arg = mock_pub.call_args[0][0]
        from src.events.schemas import EventType

        assert event_arg.event_type == EventType.MODERATION_ACTION_PROPOSED

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, modaction_community_server, modaction_request):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v2/moderation-actions", json=body)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_invalid_classifier_evidence_rejected(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        body["classifier_evidence"] = {"labels": ["hate_speech"]}

        with patch("src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock):
            response = await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        assert response.status_code == 422


class TestModerationActionsGetSingle:
    """GET /api/v2/moderation-actions/{action_id}"""

    @pytest.mark.asyncio
    async def test_get_single_returns_jsonapi_shape(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            create_resp = await modaction_auth_client.post("/api/v2/moderation-actions", json=body)
        assert create_resp.status_code == 201
        action_id = create_resp.json()["data"]["id"]

        get_resp = await modaction_auth_client.get(f"/api/v2/moderation-actions/{action_id}")
        assert get_resp.status_code == 200

        data = get_resp.json()
        assert "data" in data
        assert "jsonapi" in data
        assert data["jsonapi"]["version"] == "1.1"

        resource = data["data"]
        assert resource["type"] == "moderation-actions"
        assert resource["id"] == action_id
        attrs = resource["attributes"]
        assert "classifier_evidence" in attrs
        assert attrs["classifier_evidence"]["scores"] == [0.95]

    @pytest.mark.asyncio
    async def test_get_single_not_found_returns_404(self, modaction_auth_client):
        response = await modaction_auth_client.get(f"/api/v2/moderation-actions/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_single_requires_auth(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            create_resp = await modaction_auth_client.post("/api/v2/moderation-actions", json=body)
        action_id = create_resp.json()["data"]["id"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"/api/v2/moderation-actions/{action_id}")
        assert response.status_code == 401


class TestModerationActionsGetList:
    """GET /api/v2/moderation-actions"""

    @pytest.mark.asyncio
    async def test_list_returns_jsonapi_list_shape(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        response = await modaction_auth_client.get(
            f"/api/v2/moderation-actions?community_server_id={modaction_community_server['uuid']}"
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "jsonapi" in data
        assert data["jsonapi"]["version"] == "1.1"
        assert "meta" in data
        assert len(data["data"]) >= 1

    @pytest.mark.asyncio
    async def test_list_filter_by_action_state(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        response = await modaction_auth_client.get(
            f"/api/v2/moderation-actions"
            f"?community_server_id={modaction_community_server['uuid']}"
            f"&action_state={ActionState.PROPOSED.value}"
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["data"]:
            assert item["attributes"]["action_state"] == ActionState.PROPOSED.value

    @pytest.mark.asyncio
    async def test_list_filter_by_action_tier(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        body = _build_create_body(
            modaction_community_server["uuid"],
            modaction_request["id"],
        )
        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            await modaction_auth_client.post("/api/v2/moderation-actions", json=body)

        response = await modaction_auth_client.get(
            f"/api/v2/moderation-actions"
            f"?community_server_id={modaction_community_server['uuid']}"
            f"&action_tier={ActionTier.TIER_1_IMMEDIATE.value}"
        )
        assert response.status_code == 200
        data = response.json()
        for item in data["data"]:
            assert item["attributes"]["action_tier"] == ActionTier.TIER_1_IMMEDIATE.value

    @pytest.mark.asyncio
    async def test_list_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/moderation-actions")
        assert response.status_code == 401


class TestModerationActionsPatch:
    """PATCH /api/v2/moderation-actions/{action_id}"""

    async def _create_action(self, client, community_server_id, request_id):
        body = _build_create_body(community_server_id, request_id)
        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            resp = await client.post("/api/v2/moderation-actions", json=body)
        assert resp.status_code == 201
        return resp.json()["data"]["id"]

    @pytest.mark.asyncio
    async def test_patch_valid_transition_returns_200(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={
                    "action_state": ActionState.APPLIED.value,
                    "platform_action_id": "discord-123",
                },
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["data"]["attributes"]["action_state"] == ActionState.APPLIED.value

    @pytest.mark.asyncio
    async def test_patch_applied_publishes_applied_event(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.APPLIED.value},
            )

        assert response.status_code == 200
        from src.events.schemas import EventType

        published_types = [call[0][0].event_type for call in mock_pub.call_args_list]
        assert EventType.MODERATION_ACTION_APPLIED in published_types

    @pytest.mark.asyncio
    async def test_patch_invalid_transition_returns_422(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.CONFIRMED.value},
            )

        assert response.status_code == 422, response.text

    @pytest.mark.asyncio
    async def test_patch_not_found_returns_404(self, modaction_auth_client):
        with patch("src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock):
            response = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{uuid4()}",
                json={"action_state": ActionState.APPLIED.value},
            )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_scan_exempt_no_event(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.APPLIED.value},
            )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub2:
            mock_pub2.return_value = "test-event-id"
            resp = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.OVERTURNED.value, "overturned_reason": "mistake"},
            )
        assert resp.status_code == 200

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub3:
            mock_pub3.return_value = "test-event-id"
            resp2 = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.SCAN_EXEMPT.value},
            )
        assert resp2.status_code == 200
        assert not mock_pub3.called, "scan_exempt transition must NOT publish an event"

    @pytest.mark.asyncio
    async def test_patch_requires_auth(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.APPLIED.value},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_patch_dismissed_publishes_dismissed_event(
        self,
        modaction_auth_client,
        modaction_community_server,
        modaction_request,
    ):
        action_id = await self._create_action(
            modaction_auth_client,
            modaction_community_server["uuid"],
            modaction_request["id"],
        )

        with patch(
            "src.events.publisher.EventPublisher.publish_event", new_callable=AsyncMock
        ) as mock_pub:
            mock_pub.return_value = "test-event-id"
            response = await modaction_auth_client.patch(
                f"/api/v2/moderation-actions/{action_id}",
                json={"action_state": ActionState.DISMISSED.value},
            )

        assert response.status_code == 200
        from src.events.schemas import EventType

        published_types = [call[0][0].event_type for call in mock_pub.call_args_list]
        assert EventType.MODERATION_ACTION_DISMISSED in published_types
