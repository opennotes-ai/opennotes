from uuid import uuid4

import pendulum
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app

BASE_URL = "/api/v2/simulations"


class TestChannelMessagesUnauthenticated:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, simulation_run_factory):
        sim = await simulation_run_factory(status_val="running")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(f"{BASE_URL}/{sim['id']}/channel-messages")

        assert response.status_code == 401


class TestChannelMessagesEmpty:
    @pytest.mark.asyncio
    async def test_empty_simulation_returns_empty_data(
        self, admin_auth_client, simulation_run_factory
    ):
        sim = await simulation_run_factory(status_val="running")
        response = await admin_auth_client.get(f"{BASE_URL}/{sim['id']}/channel-messages")

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["meta"]["count"] == 0
        assert body["meta"]["has_more"] is False
        assert body["jsonapi"]["version"] == "1.1"


class TestChannelMessagesLatest:
    @pytest.mark.asyncio
    async def test_latest_messages_returned(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        for i in range(5):
            await channel_message_factory(sim["id"], inst["id"], f"msg {i}")

        response = await admin_auth_client.get(f"{BASE_URL}/{sim['id']}/channel-messages")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 5
        assert body["meta"]["count"] == 5
        assert body["meta"]["has_more"] is False

        texts = [r["attributes"]["message_text"] for r in body["data"]]
        assert texts == [f"msg {i}" for i in range(5)]

        for resource in body["data"]:
            assert resource["type"] == "sim-channel-messages"
            assert "id" in resource
            assert "message_text" in resource["attributes"]
            assert "agent_name" in resource["attributes"]
            assert "agent_profile_id" in resource["attributes"]
            assert "created_at" in resource["attributes"]


class TestChannelMessagesCursorPagination:
    @pytest.mark.asyncio
    async def test_cursor_pagination(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        created = []
        for i in range(25):
            msg = await channel_message_factory(sim["id"], inst["id"], f"msg {i}")
            created.append(msg)

        response = await admin_auth_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages",
            params={"page[size]": 20},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 20
        assert body["meta"]["has_more"] is True

        oldest_returned_id = body["data"][0]["id"]

        response2 = await admin_auth_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages",
            params={"page[size]": 20, "before": oldest_returned_id},
        )

        assert response2.status_code == 200
        body2 = response2.json()
        assert len(body2["data"]) == 5
        assert body2["meta"]["has_more"] is False

        page2_ids = {r["id"] for r in body2["data"]}
        page1_ids = {r["id"] for r in body["data"]}
        assert page2_ids.isdisjoint(page1_ids)


class TestChannelMessagesAgentName:
    @pytest.mark.asyncio
    async def test_agent_name_populated(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        await channel_message_factory(sim["id"], inst["id"], "hello world")

        response = await admin_auth_client.get(f"{BASE_URL}/{sim['id']}/channel-messages")

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1

        attrs = body["data"][0]["attributes"]
        assert attrs["agent_name"] == inst["agent_name"]
        assert attrs["agent_profile_id"] == str(inst["agent_profile_id"])


class TestChannelMessagesHasMore:
    @pytest.mark.asyncio
    async def test_has_more_false_partial_page(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        for i in range(3):
            await channel_message_factory(sim["id"], inst["id"], f"msg {i}")

        response = await admin_auth_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages",
            params={"page[size]": 20},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 3
        assert body["meta"]["has_more"] is False


class TestChannelMessagesHasMoreBoundary:
    @pytest.mark.asyncio
    async def test_has_more_false_when_exactly_page_size(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        page_size = 5
        for i in range(page_size):
            await channel_message_factory(sim["id"], inst["id"], f"msg {i}")

        response = await admin_auth_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages",
            params={"page[size]": page_size},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == page_size
        assert body["meta"]["has_more"] is False

    @pytest.mark.asyncio
    async def test_has_more_true_when_more_than_page_size(
        self,
        admin_auth_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running")
        inst = await agent_instance_factory(sim["id"])

        page_size = 5
        for i in range(page_size + 1):
            await channel_message_factory(sim["id"], inst["id"], f"msg {i}")

        response = await admin_auth_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages",
            params={"page[size]": page_size},
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == page_size
        assert body["meta"]["has_more"] is True


class TestChannelMessagesScopedKey:
    @pytest.fixture
    async def service_account_scoped_client(self):
        from src.auth.models import APIKeyCreate
        from src.database import get_session_maker
        from src.users.crud import create_api_key
        from src.users.models import User

        unique = uuid4().hex[:8]
        async with get_session_maker()() as session:
            user = User(
                username=f"svc_{unique}",
                email=f"svc_{unique}@example.com",
                hashed_password="unused-placeholder",
                is_active=True,
                is_service_account=True,
            )
            session.add(user)
            await session.flush()

            _, raw_key = await create_api_key(
                db=session,
                user_id=user.id,
                api_key_create=APIKeyCreate(
                    name="scoped-sim-key",
                    expires_in_days=30,
                    scopes=["simulations:read"],
                ),
            )
            await session.commit()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"X-API-Key": raw_key})
            yield client

    @pytest.mark.asyncio
    async def test_scoped_key_private_sim_returns_404(
        self,
        service_account_scoped_client,
        simulation_run_factory,
    ):
        sim = await simulation_run_factory(status_val="running")

        response = await service_account_scoped_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages"
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_scoped_key_public_sim_returns_200(
        self,
        service_account_scoped_client,
        simulation_run_factory,
        agent_instance_factory,
        channel_message_factory,
    ):
        sim = await simulation_run_factory(status_val="running", is_public=True)
        inst = await agent_instance_factory(sim["id"])
        await channel_message_factory(sim["id"], inst["id"], "public msg")

        response = await service_account_scoped_client.get(
            f"{BASE_URL}/{sim['id']}/channel-messages"
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["attributes"]["message_text"] == "public msg"

    @pytest.mark.asyncio
    async def test_deleted_simulation_returns_404(
        self,
        admin_auth_client,
        simulation_run_factory,
    ):
        from src.database import get_session_maker
        from src.simulation.models import SimulationRun

        sim = await simulation_run_factory(status_val="running")

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationRun).where(SimulationRun.id == sim["id"])
            )
            run = result.scalar_one()
            run.deleted_at = pendulum.now("UTC")
            await session.commit()

        response = await admin_auth_client.get(f"{BASE_URL}/{sim['id']}/channel-messages")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_simulation_returns_404(
        self,
        admin_auth_client,
    ):
        random_id = uuid4()

        response = await admin_auth_client.get(f"{BASE_URL}/{random_id}/channel-messages")

        assert response.status_code == 404
