from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


class TestOrchestratorsJSONAPICreate:
    @pytest.mark.asyncio
    async def test_create_orchestrator_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        request_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"TestOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                    "agent_profile_ids": [],
                    "scoring_config": {},
                },
            }
        }

        response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "simulation-orchestrators"
        assert isinstance(data["data"]["id"], str)
        assert data["data"]["attributes"]["name"] == f"TestOrch_{unique}"
        assert data["data"]["attributes"]["turn_cadence_seconds"] == 60
        assert data["data"]["attributes"]["max_agents"] == 10
        assert data["data"]["attributes"]["removal_rate"] == 0.1
        assert data["data"]["attributes"]["max_turns_per_agent"] == 100
        assert data["data"]["attributes"]["is_active"] is True

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_orchestrator_jsonapi_missing_required_field(self, admin_auth_client):
        request_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }

        response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=request_body
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_orchestrator_jsonapi_unauthenticated(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            request_body = {
                "data": {
                    "type": "simulation-orchestrators",
                    "attributes": {
                        "name": "Unauth Orch",
                        "turn_cadence_seconds": 60,
                        "max_agents": 10,
                        "removal_rate": 0.1,
                        "max_turns_per_agent": 100,
                    },
                }
            }
            response = await client.post("/api/v2/simulation-orchestrators", json=request_body)
            assert response.status_code == 401


class TestOrchestratorsJSONAPIList:
    @pytest.mark.asyncio
    async def test_list_orchestrators_jsonapi(self, admin_auth_client):
        response = await admin_auth_client.get("/api/v2/simulation-orchestrators")

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
    async def test_list_orchestrators_jsonapi_pagination(self, admin_auth_client):
        response = await admin_auth_client.get(
            "/api/v2/simulation-orchestrators?page[number]=1&page[size]=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_orchestrators_jsonapi_returns_created(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"ListTestOrch_{unique}",
                    "turn_cadence_seconds": 30,
                    "max_agents": 5,
                    "removal_rate": 0.0,
                    "max_turns_per_agent": 50,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201

        response = await admin_auth_client.get("/api/v2/simulation-orchestrators")
        assert response.status_code == 200

        data = response.json()
        names = [r["attributes"]["name"] for r in data["data"]]
        assert f"ListTestOrch_{unique}" in names


class TestOrchestratorsJSONAPIGet:
    @pytest.mark.asyncio
    async def test_get_orchestrator_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"GetTestOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await admin_auth_client.get(f"/api/v2/simulation-orchestrators/{created_id}")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "simulation-orchestrators"
        assert data["data"]["id"] == created_id
        assert "attributes" in data["data"]
        assert data["data"]["attributes"]["name"] == f"GetTestOrch_{unique}"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_get_orchestrator_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.get(f"/api/v2/simulation-orchestrators/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data


class TestOrchestratorsJSONAPIUpdate:
    @pytest.mark.asyncio
    async def test_update_orchestrator_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"UpdateTestOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "simulation-orchestrators",
                "id": created_id,
                "attributes": {
                    "name": f"UpdatedOrch_{unique}",
                    "max_agents": 20,
                },
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulation-orchestrators/{created_id}", json=update_body
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert data["data"]["type"] == "simulation-orchestrators"
        assert data["data"]["id"] == created_id
        assert data["data"]["attributes"]["name"] == f"UpdatedOrch_{unique}"
        assert data["data"]["attributes"]["max_agents"] == 20
        assert data["data"]["attributes"]["turn_cadence_seconds"] == 60

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_orchestrator_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        update_body = {
            "data": {
                "type": "simulation-orchestrators",
                "id": fake_id,
                "attributes": {
                    "name": "Should not work",
                },
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulation-orchestrators/{fake_id}", json=update_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_update_orchestrator_jsonapi_id_mismatch(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"MismatchOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        update_body = {
            "data": {
                "type": "simulation-orchestrators",
                "id": str(uuid4()),
                "attributes": {
                    "name": "Should not work",
                },
            }
        }

        response = await admin_auth_client.patch(
            f"/api/v2/simulation-orchestrators/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestOrchestratorsJSONAPIDelete:
    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"DeleteTestOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await admin_auth_client.delete(f"/api/v2/simulation-orchestrators/{created_id}")

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi_not_found(self, admin_auth_client):
        fake_id = str(uuid4())

        response = await admin_auth_client.delete(f"/api/v2/simulation-orchestrators/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi_soft_delete(self, admin_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "simulation-orchestrators",
                "attributes": {
                    "name": f"SoftDeleteOrch_{unique}",
                    "turn_cadence_seconds": 60,
                    "max_agents": 10,
                    "removal_rate": 0.1,
                    "max_turns_per_agent": 100,
                },
            }
        }
        create_response = await admin_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        delete_response = await admin_auth_client.delete(
            f"/api/v2/simulation-orchestrators/{created_id}"
        )
        assert delete_response.status_code == 204

        get_response = await admin_auth_client.get(f"/api/v2/simulation-orchestrators/{created_id}")
        assert get_response.status_code == 404

        from sqlalchemy import select

        from src.database import get_session_maker
        from src.simulation.models import SimulationOrchestrator

        async with get_session_maker()() as session:
            result = await session.execute(
                select(SimulationOrchestrator).where(SimulationOrchestrator.id == UUID(created_id))
            )
            orch = result.scalar_one_or_none()
            assert orch is not None, "Row should still exist in DB"
            assert orch.deleted_at is not None, "deleted_at should be set"
