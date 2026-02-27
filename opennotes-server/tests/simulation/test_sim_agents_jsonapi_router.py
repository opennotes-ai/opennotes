from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


class TestSimAgentsJSONAPICreate:
    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"TestAgent_{unique}",
                    "personality": "A helpful test agent",
                    "model_name": "openai:gpt-4o",
                },
            }
        }

        response = await admin_auth_client.post("/api/v2/sim-agents", json=request_body)

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "sim-agents"
        assert isinstance(data["data"]["id"], str)
        assert data["data"]["attributes"]["name"] == f"TestAgent_{unique}"
        assert data["data"]["attributes"]["personality"] == "A helpful test agent"
        assert data["data"]["attributes"]["model_name"] == {"provider": "openai", "model": "gpt-4o"}
        assert data["data"]["attributes"]["memory_compaction_strategy"] == "sliding_window"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi_with_optional_fields(self, admin_auth_client):
        unique = uuid4().hex[:8]
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"FullAgent_{unique}",
                    "personality": "A detailed test agent",
                    "model_name": "openai:gpt-4o",
                    "model_params": {"temperature": 0.7, "max_tokens": 1000},
                    "tool_config": {"tools": ["search"]},
                    "memory_compaction_strategy": "summarize_and_prune",
                },
            }
        }

        response = await admin_auth_client.post("/api/v2/sim-agents", json=request_body)

        assert response.status_code == 201
        data = response.json()
        attrs = data["data"]["attributes"]
        assert attrs["model_params"] == {"temperature": 0.7, "max_tokens": 1000}
        assert attrs["tool_config"] == {"tools": ["search"]}
        assert attrs["memory_compaction_strategy"] == "summarize_and_prune"

    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi_missing_required_field(self, admin_auth_client):
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "personality": "Missing name field",
                    "model_name": "openai:gpt-4o",
                },
            }
        }

        response = await admin_auth_client.post("/api/v2/sim-agents", json=request_body)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = {
                "data": {
                    "type": "sim-agents",
                    "attributes": {
                        "name": "Unauth Agent",
                        "personality": "Should fail",
                        "model_name": "openai:gpt-4o",
                    },
                }
            }
            response = await client.post("/api/v2/sim-agents", json=request_body)
            assert response.status_code == 401


class TestSimAgentsJSONAPIList:
    @pytest.mark.asyncio
    async def test_list_sim_agents_jsonapi(self, admin_auth_client):
        response = await admin_auth_client.get("/api/v2/sim-agents")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        assert "jsonapi" in data
        assert data["jsonapi"].get("version") == "1.1"
        assert "links" in data

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_list_sim_agents_jsonapi_pagination(self, admin_auth_client):
        response = await admin_auth_client.get("/api/v2/sim-agents?page[number]=1&page[size]=5")

        assert response.status_code == 200
        data = response.json()
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_sim_agents_jsonapi_returns_created(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"ListTestAgent_{unique}",
                    "personality": "For list test",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201

        response = await admin_auth_client.get("/api/v2/sim-agents")
        assert response.status_code == 200

        data = response.json()
        names = [r["attributes"]["name"] for r in data["data"]]
        assert f"ListTestAgent_{unique}" in names


class TestSimAgentsJSONAPIGet:
    @pytest.mark.asyncio
    async def test_get_sim_agent_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"GetTestAgent_{unique}",
                    "personality": "For get test",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await admin_auth_client.get(f"/api/v2/sim-agents/{created_id}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "sim-agents"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["name"] == f"GetTestAgent_{unique}"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_sim_agent_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.get(f"/api/v2/sim-agents/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data


class TestSimAgentsJSONAPIUpdate:
    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"UpdateTestAgent_{unique}",
                    "personality": "Original personality",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "sim-agents",
                "id": created_id,
                "attributes": {
                    "name": f"UpdatedAgent_{unique}",
                    "personality": "Updated personality",
                },
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/sim-agents/{created_id}", json=update_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["type"] == "sim-agents"
        assert data["data"]["id"] == created_id
        assert data["data"]["attributes"]["name"] == f"UpdatedAgent_{unique}"
        assert data["data"]["attributes"]["personality"] == "Updated personality"
        assert data["data"]["attributes"]["model_name"] == {"provider": "openai", "model": "gpt-4o"}

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        update_body = {
            "data": {
                "type": "sim-agents",
                "id": fake_id,
                "attributes": {
                    "name": "Should not work",
                },
            }
        }

        response = await admin_auth_client.patch(f"/api/v2/sim-agents/{fake_id}", json=update_body)

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi_id_mismatch(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"MismatchAgent_{unique}",
                    "personality": "For mismatch test",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "sim-agents",
                "id": str(uuid4()),
                "attributes": {
                    "name": "Should not work",
                },
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/sim-agents/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestSimAgentsJSONAPIDelete:
    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"DeleteTestAgent_{unique}",
                    "personality": "For delete test",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await admin_auth_client.delete(f"/api/v2/sim-agents/{created_id}")

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.delete(f"/api/v2/sim-agents/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi_soft_delete(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"SoftDeleteAgent_{unique}",
                    "personality": "For soft delete test",
                    "model_name": "openai:gpt-4o",
                },
            }
        }
        create_response = await admin_auth_client.post("/api/v2/sim-agents", json=create_body)
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        delete_response = await admin_auth_client.delete(f"/api/v2/sim-agents/{created_id}")
        assert delete_response.status_code == 204

        get_response = await admin_auth_client.get(f"/api/v2/sim-agents/{created_id}")
        assert get_response.status_code == 404

        from sqlalchemy import select

        from src.database import get_session_maker
        from src.simulation.models import SimAgent

        async with get_session_maker()() as session:
            result = await session.execute(select(SimAgent).where(SimAgent.id == UUID(created_id)))
            agent = result.scalar_one_or_none()
            assert agent is not None, "Row should still exist in DB"
            assert agent.deleted_at is not None, "deleted_at should be set"
