from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def orchestrators_jsonapi_test_user():
    return {
        "username": f"orch_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"orch_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "Orchestrators JSONAPI Test User",
    }


@pytest.fixture
async def orchestrators_jsonapi_registered_user(orchestrators_jsonapi_test_user):
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=orchestrators_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == orchestrators_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"orch_jsonapi_discord_{uuid4().hex[:8]}"

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

            await session.commit()
            await session.refresh(user)
            await session.refresh(profile)

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "is_active": user.is_active,
                "is_superuser": user.is_superuser,
                "discord_id": user.discord_id,
                "profile_id": profile.id,
            }


@pytest.fixture
async def orchestrators_jsonapi_auth_headers(orchestrators_jsonapi_registered_user):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(orchestrators_jsonapi_registered_user["id"]),
        "username": orchestrators_jsonapi_registered_user["username"],
        "role": orchestrators_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def orchestrators_jsonapi_auth_client(orchestrators_jsonapi_auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(orchestrators_jsonapi_auth_headers)
        yield client


class TestOrchestratorsJSONAPICreate:
    @pytest.mark.asyncio
    async def test_create_orchestrator_jsonapi(self, orchestrators_jsonapi_auth_client):
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

        response = await orchestrators_jsonapi_auth_client.post(
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
    async def test_create_orchestrator_jsonapi_missing_required_field(
        self, orchestrators_jsonapi_auth_client
    ):
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

        response = await orchestrators_jsonapi_auth_client.post(
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
    async def test_list_orchestrators_jsonapi(self, orchestrators_jsonapi_auth_client):
        response = await orchestrators_jsonapi_auth_client.get("/api/v2/simulation-orchestrators")

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
    async def test_list_orchestrators_jsonapi_pagination(self, orchestrators_jsonapi_auth_client):
        response = await orchestrators_jsonapi_auth_client.get(
            "/api/v2/simulation-orchestrators?page[number]=1&page[size]=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_orchestrators_jsonapi_returns_created(
        self, orchestrators_jsonapi_auth_client
    ):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201

        response = await orchestrators_jsonapi_auth_client.get("/api/v2/simulation-orchestrators")
        assert response.status_code == 200

        data = response.json()
        names = [r["attributes"]["name"] for r in data["data"]]
        assert f"ListTestOrch_{unique}" in names


class TestOrchestratorsJSONAPIGet:
    @pytest.mark.asyncio
    async def test_get_orchestrator_jsonapi(self, orchestrators_jsonapi_auth_client):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await orchestrators_jsonapi_auth_client.get(
            f"/api/v2/simulation-orchestrators/{created_id}"
        )

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
    async def test_get_orchestrator_jsonapi_not_found(self, orchestrators_jsonapi_auth_client):
        fake_id = str(uuid4())

        response = await orchestrators_jsonapi_auth_client.get(
            f"/api/v2/simulation-orchestrators/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data


class TestOrchestratorsJSONAPIUpdate:
    @pytest.mark.asyncio
    async def test_update_orchestrator_jsonapi(self, orchestrators_jsonapi_auth_client):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
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

        response = await orchestrators_jsonapi_auth_client.patch(
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
    async def test_update_orchestrator_jsonapi_not_found(self, orchestrators_jsonapi_auth_client):
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

        response = await orchestrators_jsonapi_auth_client.patch(
            f"/api/v2/simulation-orchestrators/{fake_id}", json=update_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_update_orchestrator_jsonapi_id_mismatch(self, orchestrators_jsonapi_auth_client):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
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

        response = await orchestrators_jsonapi_auth_client.patch(
            f"/api/v2/simulation-orchestrators/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestOrchestratorsJSONAPIDelete:
    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi(self, orchestrators_jsonapi_auth_client):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await orchestrators_jsonapi_auth_client.delete(
            f"/api/v2/simulation-orchestrators/{created_id}"
        )

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi_not_found(self, orchestrators_jsonapi_auth_client):
        fake_id = str(uuid4())

        response = await orchestrators_jsonapi_auth_client.delete(
            f"/api/v2/simulation-orchestrators/{fake_id}"
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_delete_orchestrator_jsonapi_soft_delete(self, orchestrators_jsonapi_auth_client):
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
        create_response = await orchestrators_jsonapi_auth_client.post(
            "/api/v2/simulation-orchestrators", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        delete_response = await orchestrators_jsonapi_auth_client.delete(
            f"/api/v2/simulation-orchestrators/{created_id}"
        )
        assert delete_response.status_code == 204

        get_response = await orchestrators_jsonapi_auth_client.get(
            f"/api/v2/simulation-orchestrators/{created_id}"
        )
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
