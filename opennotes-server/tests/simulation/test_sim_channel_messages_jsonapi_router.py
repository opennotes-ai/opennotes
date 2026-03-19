import pytest
from httpx import ASGITransport, AsyncClient

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
