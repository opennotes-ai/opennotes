import json
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.notes.schemas import NoteClassification


@pytest.fixture
async def nats_event_community_server():
    from uuid import uuid4

    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    community_server_id = uuid4()
    platform_id = "987654321098765432"
    async with get_session_maker()() as db:
        community_server = CommunityServer(
            id=community_server_id,
            platform="discord",
            platform_community_server_id=platform_id,
            name="Test Guild for NATS Event",
        )
        db.add(community_server)
        await db.commit()

    return {"uuid": community_server_id, "platform_community_server_id": platform_id}


@pytest.fixture
async def nats_event_registered_user(nats_event_community_server):
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import CommunityMember, UserIdentity, UserProfile

    test_user = {
        "username": f"natseventuser_{datetime.now(tz=UTC).timestamp()}",
        "email": f"natsevent_{datetime.now(tz=UTC).timestamp()}@example.com",
        "password": "TestPassword123!",
        "full_name": "NATS Event Test User",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"natsevent_discord_{datetime.now(tz=UTC).timestamp()}"

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
                community_id=nats_event_community_server["uuid"],
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
                "role": user.role,
                "profile_id": profile.id,
            }


@pytest.fixture
async def nats_event_admin_client(nats_event_registered_user):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(nats_event_registered_user["id"]),
        "username": nats_event_registered_user["username"],
        "role": nats_event_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(headers)
        yield client


class TestForcePublishNATSEvent:
    @pytest.mark.asyncio
    async def test_force_publish_publishes_platform_snowflake_not_uuid(
        self,
        nats_event_admin_client,
        nats_event_community_server,
        nats_event_registered_user,
    ):
        from src.events.nats_client import nats_client

        note_data = {
            "data": {
                "type": "notes",
                "attributes": {
                    "summary": f"NATS event test note {int(datetime.now(tz=UTC).timestamp() * 1000000)}",
                    "classification": NoteClassification.NOT_MISLEADING.value,
                    "community_server_id": str(nats_event_community_server["uuid"]),
                    "author_id": str(nats_event_registered_user["profile_id"]),
                },
            }
        }
        create_response = await nats_event_admin_client.post("/api/v2/notes", json=note_data)
        assert create_response.status_code == 201, f"Failed to create note: {create_response.text}"
        note_id = create_response.json()["data"]["id"]

        nats_client.publish.reset_mock()

        response = await nats_event_admin_client.post(f"/api/v2/notes/{note_id}/force-publish")
        assert response.status_code == 200, f"Force-publish failed: {response.text}"

        assert nats_client.publish.called, "Expected NATS publish to be called"

        published_calls = nats_client.publish.call_args_list
        score_update_call = None
        for call in published_calls:
            subject = call.args[0] if call.args else call.kwargs.get("subject", "")
            if "score_updated" in subject:
                score_update_call = call
                break

        assert score_update_call is not None, (
            f"Expected a note.score.updated NATS publish call, got subjects: "
            f"{[c.args[0] for c in published_calls]}"
        )

        event_data = json.loads(score_update_call.args[1])

        expected_platform_id = nats_event_community_server["platform_community_server_id"]
        internal_uuid = str(nats_event_community_server["uuid"])

        assert event_data["community_server_id"] != internal_uuid, (
            f"community_server_id should NOT be the internal UUID ({internal_uuid}), but it is"
        )
        assert event_data["community_server_id"] == expected_platform_id, (
            f"community_server_id should be the platform snowflake ({expected_platform_id}), "
            f"got: {event_data['community_server_id']}"
        )
