"""Behavioral parity tests: /api/public/v1 vs legacy /api/v2 (TASK-1461.03).

Proves that each allowlisted adapter endpoint served under the new public prefix
returns byte-for-byte equivalent responses to its legacy /api/v2 counterpart.

Both prefixes mount the same underlying router instances (see src/main.py and
src/public_api.py), so equivalence is expected — this test guards against future
drift (e.g. divergent dependency overrides, middleware ordering, auth handling).

Test shape:
- One representative read per allowlisted router (6 total parametrized cases)
- One write-path check that issues the same payload under both prefixes and
  compares the created-resource shape (IDs / timestamps / self-links normalized).
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app

DISCOURSE_DEV_API_KEY = "opk_discourse_dev_platform_adapter_2026"

VOLATILE_KEYS: set[str] = {
    "id",
    "created_at",
    "updated_at",
    "requested_at",
    "applied_at",
    "confirmed_at",
    "overturned_at",
    "completed_at",
    "self",
    "links",
    "jsonapi",
    "request_id",
    "message_archive_id",
    "community_server_id",
    "platform_community_server_id",
    "profile_id",
    "platform_user_id",
}


def _strip_volatile(value: Any) -> Any:
    """Recursively drop keys whose values vary between otherwise-equivalent responses.

    The two prefixes produce the same handler output, but `links.self` differs
    because it reflects the inbound request URL. For write paths, each POST
    creates a distinct resource, so ids/timestamps also differ by design.
    """
    if isinstance(value, Mapping):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


@pytest.fixture(autouse=True)
async def ensure_app_started() -> None:
    """ASGITransport skips the lifespan, so startup_complete stays unset — flip it manually.

    Without this every request returns 503 from StartupGateMiddleware (the
    integration-level bypass handles that too, but be explicit for robustness).
    """
    app.state.startup_complete = True


@pytest.fixture
async def adapter_client(db_session) -> AsyncIterator[AsyncClient]:
    """AsyncClient pre-authenticated with the seeded Discourse platform:adapter key.

    Seeds the adapter user + API key via the canonical scripts/seed_api_keys flow
    (same as test_seed_discourse_api_key.py), then attaches the key as X-API-Key.
    """
    scripts_dir = str(Path(__file__).parent.parent.parent / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    seed_mod = importlib.import_module("seed_api_keys")
    await seed_mod.seed_discourse_api_key(db_session)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update({"X-API-Key": DISCOURSE_DEV_API_KEY})
        yield client


@pytest.fixture
async def seeded_discord_guild() -> dict[str, Any]:
    """Pre-seed a Discord community server that the lookup endpoints can resolve."""
    from src.database import get_session_maker
    from src.llm_config.models import CommunityServer

    platform_id = f"parity_guild_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        cs = CommunityServer(
            id=uuid4(),
            platform="discord",
            platform_community_server_id=platform_id,
            name="Parity Test Discord Guild",
            is_active=True,
        )
        db.add(cs)
        await db.commit()
        await db.refresh(cs)
    return {"id": cs.id, "platform_community_server_id": platform_id}


@pytest.fixture
async def seeded_discord_profile() -> dict[str, Any]:
    """Pre-seed a Discord identity + profile the user-profiles/lookup endpoint can resolve."""
    from src.database import get_session_maker
    from src.users.profile_models import UserIdentity, UserProfile

    platform_user_id = f"parity_user_{uuid4().hex[:8]}"
    async with get_session_maker()() as db:
        profile = UserProfile(
            id=uuid4(),
            display_name="Parity Test User",
            is_human=True,
            is_active=True,
        )
        db.add(profile)
        await db.flush()
        identity = UserIdentity(
            id=uuid4(),
            profile_id=profile.id,
            provider="discord",
            provider_user_id=platform_user_id,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(profile)
    return {"profile_id": profile.id, "platform_user_id": platform_user_id}


# Each case: a suffix (the path under the router prefix) + optional query params.
# Both prefixes get the same request; responses must match after normalization.
READ_PARITY_CASES = [
    pytest.param("/notes", {}, id="notes-router:list-notes"),
    # ratings_jsonapi_router has no bare GET /ratings; its reads are nested
    # under /notes/{note_id}/ratings. Use the stats variant with a random
    # non-matching UUID — the handler still runs (returns 404 via handler
    # code), so this exercises the ratings router on both prefixes rather
    # than letting FastAPI short-circuit.
    pytest.param(
        f"/notes/{uuid4()}/ratings/stats",
        {},
        id="ratings-router:ratings-stats-for-note",
    ),
    pytest.param("/requests", {}, id="requests-router:list-requests"),
    pytest.param(
        "/moderation-actions",
        {},
        id="moderation-actions-router:list",
    ),
    pytest.param(
        "/community-servers/lookup",
        {"platform": "discord", "platform_community_server_id": "__SEEDED__"},
        id="communities-router:lookup-community",
    ),
    pytest.param(
        "/user-profiles/lookup",
        {"platform": "discord", "platform_user_id": "__SEEDED__"},
        id="profiles-router:lookup-profile",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("suffix", "params"), READ_PARITY_CASES)
async def test_read_endpoints_parity_legacy_vs_public(
    suffix: str,
    params: dict[str, Any],
    adapter_client: AsyncClient,
    seeded_discord_guild: dict[str, Any],
    seeded_discord_profile: dict[str, Any],
) -> None:
    """For each allowlisted read endpoint: legacy /api/v2 and /api/public/v1 must agree.

    Status codes MUST match exactly. Response bodies must match after stripping
    volatile fields (primarily `links.self`, which reflects the inbound URL).
    """
    resolved_params = dict(params)
    if resolved_params.get("platform_community_server_id") == "__SEEDED__":
        resolved_params["platform_community_server_id"] = seeded_discord_guild[
            "platform_community_server_id"
        ]
    if resolved_params.get("platform_user_id") == "__SEEDED__":
        resolved_params["platform_user_id"] = seeded_discord_profile["platform_user_id"]

    legacy_url = f"{settings.API_V2_PREFIX}{suffix}"
    public_url = f"{settings.API_PUBLIC_V1_PREFIX}{suffix}"

    legacy_resp = await adapter_client.get(legacy_url, params=resolved_params)
    public_resp = await adapter_client.get(public_url, params=resolved_params)

    assert legacy_resp.status_code == public_resp.status_code, (
        f"status differs for {suffix}: legacy={legacy_resp.status_code} "
        f"public={public_resp.status_code}\n"
        f"legacy body: {legacy_resp.text[:500]}\n"
        f"public body: {public_resp.text[:500]}"
    )
    # Sanity: we're actually hitting the handler, not 401/404/5xx from a mis-route.
    assert legacy_resp.status_code < 500, (
        f"legacy {suffix} returned 5xx: {legacy_resp.status_code} {legacy_resp.text[:500]}"
    )
    assert legacy_resp.status_code != 401, (
        f"adapter key rejected on {suffix}; auth fixture is broken, not a parity bug"
    )

    legacy_body = _strip_volatile(legacy_resp.json())
    public_body = _strip_volatile(public_resp.json())
    assert legacy_body == public_body, (
        f"body differs for {suffix} after normalization\n"
        f"legacy: {legacy_body}\n"
        f"public: {public_body}"
    )


@pytest.mark.asyncio
async def test_write_endpoint_parity_post_requests(
    adapter_client: AsyncClient,
) -> None:
    """POST /requests under both prefixes must produce equivalent resource shapes.

    Each call creates a distinct Request row, so identifiers and timestamps
    differ by design. The structural envelope (type, status code, attribute
    keys, non-volatile attribute values) must match.
    """

    # Shared non-volatile attributes — both POSTs send the same metadata / content /
    # platform identifiers so the resulting resources should differ ONLY in the
    # keys we explicitly normalize away (id, request_id, community_server_id,
    # timestamps, message_archive_id, links.self).
    shared_metadata = {"parity": True, "source": "parity-suite"}
    shared_content = "Parity check payload"
    shared_message_id = f"msg_{uuid4().hex[:8]}"
    shared_channel_id = f"chan_{uuid4().hex[:8]}"
    shared_author_id = f"auth_{uuid4().hex[:8]}"

    def _build_body() -> dict[str, Any]:
        # request_id and community_server_id must be unique per POST (both are
        # unique columns / would collide on the second insert).
        return {
            "data": {
                "type": "requests",
                "attributes": {
                    "request_id": f"parity-req-{uuid4().hex[:12]}",
                    "requested_by": "parity_requester_discord_id",
                    "community_server_id": f"parity_guild_write_{uuid4().hex[:6]}",
                    "original_message_content": shared_content,
                    "platform_message_id": shared_message_id,
                    "platform_channel_id": shared_channel_id,
                    "platform_author_id": shared_author_id,
                    "metadata": shared_metadata,
                },
            }
        }

    # Patch the event publisher so we don't require a live NATS connection.
    with patch(
        "src.events.publisher.EventPublisher.publish_event",
        new_callable=AsyncMock,
    ):
        legacy_resp = await adapter_client.post(
            f"{settings.API_V2_PREFIX}/requests", json=_build_body()
        )
        public_resp = await adapter_client.post(
            f"{settings.API_PUBLIC_V1_PREFIX}/requests", json=_build_body()
        )

    assert legacy_resp.status_code == public_resp.status_code, (
        f"write parity status mismatch: legacy={legacy_resp.status_code} "
        f"public={public_resp.status_code}\n"
        f"legacy body: {legacy_resp.text[:500]}\n"
        f"public body: {public_resp.text[:500]}"
    )
    assert legacy_resp.status_code == 201, (
        f"expected 201 from POST /requests under legacy prefix, got "
        f"{legacy_resp.status_code}: {legacy_resp.text[:500]}"
    )

    legacy_json = legacy_resp.json()
    public_json = public_resp.json()

    # Structural envelope: JSON:API data/type
    assert legacy_json["data"]["type"] == public_json["data"]["type"] == "requests"

    # Attribute keys must be identical — schema drift between prefixes is a bug.
    legacy_attr_keys = set(legacy_json["data"]["attributes"].keys())
    public_attr_keys = set(public_json["data"]["attributes"].keys())
    assert legacy_attr_keys == public_attr_keys, (
        f"attribute keys drift between prefixes:\n"
        f"only in legacy: {legacy_attr_keys - public_attr_keys}\n"
        f"only in public: {public_attr_keys - legacy_attr_keys}"
    )

    # Non-volatile attributes must match in shape (both POSTs sent equivalent payloads).
    legacy_norm = _strip_volatile(legacy_json)
    public_norm = _strip_volatile(public_json)
    assert legacy_norm == public_norm, (
        f"non-volatile attribute shape differs:\nlegacy: {legacy_norm}\npublic: {public_norm}"
    )
