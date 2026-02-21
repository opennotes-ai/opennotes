from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def sim_agents_jsonapi_test_user():
    return {
        "username": f"sim_agents_jsonapi_user_{uuid4().hex[:8]}",
        "email": f"sim_agents_jsonapi_{uuid4().hex[:8]}@example.com",
        "password": "TestPassword123!",
        "full_name": "SimAgents JSONAPI Test User",
    }


@pytest.fixture
async def sim_agents_jsonapi_registered_user(sim_agents_jsonapi_test_user):
    from sqlalchemy import select

    from src.database import get_session_maker
    from src.users.models import User
    from src.users.profile_models import UserIdentity, UserProfile

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=sim_agents_jsonapi_test_user)

        async with get_session_maker()() as session:
            stmt = select(User).where(User.username == sim_agents_jsonapi_test_user["username"])
            result = await session.execute(stmt)
            user = result.scalar_one()

            user.discord_id = f"sim_agents_jsonapi_discord_{uuid4().hex[:8]}"

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
async def sim_agents_jsonapi_auth_headers(sim_agents_jsonapi_registered_user):
    from src.auth.auth import create_access_token

    token_data = {
        "sub": str(sim_agents_jsonapi_registered_user["id"]),
        "username": sim_agents_jsonapi_registered_user["username"],
        "role": sim_agents_jsonapi_registered_user["role"],
    }
    access_token = create_access_token(token_data)
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def sim_agents_jsonapi_auth_client(sim_agents_jsonapi_auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(sim_agents_jsonapi_auth_headers)
        yield client


class TestSimAgentsJSONAPICreate:
    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"TestAgent_{unique}",
                    "personality": "A helpful test agent",
                    "model_name": "gpt-4o",
                },
            }
        }

        response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=request_body
        )

        assert response.status_code == 201, (
            f"Expected 201, got {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        assert data["data"]["type"] == "sim-agents"
        assert isinstance(data["data"]["id"], str)
        assert data["data"]["attributes"]["name"] == f"TestAgent_{unique}"
        assert data["data"]["attributes"]["personality"] == "A helpful test agent"
        assert data["data"]["attributes"]["model_name"] == "gpt-4o"
        assert data["data"]["attributes"]["memory_compaction_strategy"] == "sliding_window"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi_with_optional_fields(
        self, sim_agents_jsonapi_auth_client
    ):
        unique = uuid4().hex[:8]
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"FullAgent_{unique}",
                    "personality": "A detailed test agent",
                    "model_name": "gpt-4o",
                    "model_params": {"temperature": 0.7, "max_tokens": 1000},
                    "tool_config": {"tools": ["search"]},
                    "memory_compaction_strategy": "summarize",
                },
            }
        }

        response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=request_body
        )

        assert response.status_code == 201
        data = response.json()
        attrs = data["data"]["attributes"]
        assert attrs["model_params"] == {"temperature": 0.7, "max_tokens": 1000}
        assert attrs["tool_config"] == {"tools": ["search"]}
        assert attrs["memory_compaction_strategy"] == "summarize"

    @pytest.mark.asyncio
    async def test_create_sim_agent_jsonapi_missing_required_field(
        self, sim_agents_jsonapi_auth_client
    ):
        request_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "personality": "Missing name field",
                    "model_name": "gpt-4o",
                },
            }
        }

        response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=request_body
        )

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
                        "model_name": "gpt-4o",
                    },
                }
            }
            response = await client.post("/api/v2/sim-agents", json=request_body)
            assert response.status_code == 401


class TestSimAgentsJSONAPIList:
    @pytest.mark.asyncio
    async def test_list_sim_agents_jsonapi(self, sim_agents_jsonapi_auth_client):
        response = await sim_agents_jsonapi_auth_client.get("/api/v2/sim-agents")

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
    async def test_list_sim_agents_jsonapi_pagination(self, sim_agents_jsonapi_auth_client):
        response = await sim_agents_jsonapi_auth_client.get(
            "/api/v2/sim-agents?page[number]=1&page[size]=5"
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data
        assert "meta" in data
        assert "count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_sim_agents_jsonapi_returns_created(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"ListTestAgent_{unique}",
                    "personality": "For list test",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
        assert create_response.status_code == 201

        response = await sim_agents_jsonapi_auth_client.get("/api/v2/sim-agents")
        assert response.status_code == 200

        data = response.json()
        names = [r["attributes"]["name"] for r in data["data"]]
        assert f"ListTestAgent_{unique}" in names


class TestSimAgentsJSONAPIGet:
    @pytest.mark.asyncio
    async def test_get_sim_agent_jsonapi(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"GetTestAgent_{unique}",
                    "personality": "For get test",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await sim_agents_jsonapi_auth_client.get(f"/api/v2/sim-agents/{created_id}")

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
    async def test_get_sim_agent_jsonapi_not_found(self, sim_agents_jsonapi_auth_client):
        fake_id = str(uuid4())

        response = await sim_agents_jsonapi_auth_client.get(f"/api/v2/sim-agents/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data


class TestSimAgentsJSONAPIUpdate:
    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"UpdateTestAgent_{unique}",
                    "personality": "Original personality",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
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

        response = await sim_agents_jsonapi_auth_client.patch(
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
        assert data["data"]["attributes"]["model_name"] == "gpt-4o"

        content_type = response.headers.get("content-type", "")
        assert "application/vnd.api+json" in content_type

    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi_not_found(self, sim_agents_jsonapi_auth_client):
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

        response = await sim_agents_jsonapi_auth_client.patch(
            f"/api/v2/sim-agents/{fake_id}", json=update_body
        )

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_update_sim_agent_jsonapi_id_mismatch(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"MismatchAgent_{unique}",
                    "personality": "For mismatch test",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
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

        response = await sim_agents_jsonapi_auth_client.patch(
            f"/api/v2/sim-agents/{created_id}", json=update_body
        )

        assert response.status_code == 409


class TestSimAgentsJSONAPIDelete:
    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"DeleteTestAgent_{unique}",
                    "personality": "For delete test",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        response = await sim_agents_jsonapi_auth_client.delete(f"/api/v2/sim-agents/{created_id}")

        assert response.status_code == 204, (
            f"Expected 204, got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi_not_found(self, sim_agents_jsonapi_auth_client):
        fake_id = str(uuid4())

        response = await sim_agents_jsonapi_auth_client.delete(f"/api/v2/sim-agents/{fake_id}")

        assert response.status_code == 404
        data = response.json()
        assert "errors" in data

    @pytest.mark.asyncio
    async def test_delete_sim_agent_jsonapi_soft_delete(self, sim_agents_jsonapi_auth_client):
        unique = uuid4().hex[:8]
        create_body = {
            "data": {
                "type": "sim-agents",
                "attributes": {
                    "name": f"SoftDeleteAgent_{unique}",
                    "personality": "For soft delete test",
                    "model_name": "gpt-4o",
                },
            }
        }
        create_response = await sim_agents_jsonapi_auth_client.post(
            "/api/v2/sim-agents", json=create_body
        )
        assert create_response.status_code == 201
        created_id = create_response.json()["data"]["id"]

        delete_response = await sim_agents_jsonapi_auth_client.delete(
            f"/api/v2/sim-agents/{created_id}"
        )
        assert delete_response.status_code == 204

        get_response = await sim_agents_jsonapi_auth_client.get(f"/api/v2/sim-agents/{created_id}")
        assert get_response.status_code == 404

        from sqlalchemy import select

        from src.database import get_session_maker
        from src.simulation.models import SimAgent

        async with get_session_maker()() as session:
            result = await session.execute(select(SimAgent).where(SimAgent.id == UUID(created_id)))
            agent = result.scalar_one_or_none()
            assert agent is not None, "Row should still exist in DB"
            assert agent.deleted_at is not None, "deleted_at should be set"
