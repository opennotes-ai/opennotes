"""
Integration tests for outbound webhook delivery service.

Tests:
- Delivery creates WebhookDelivery record with status=delivered on success
- HMAC signature in headers is verifiable
- Retry on 500 response, mark failed after 3 attempts
- No retry on 400 response (immediate fail)
- Events filter: webhook with events=["moderation_action.proposed"] only receives that event
- Registration requires auth (401 without token)
"""

import time
import types
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import insert

from src.database import get_session_maker
from src.llm_config.models import CommunityServer
from src.main import app
from src.webhooks.delivery import OutboundWebhookDeliveryService
from src.webhooks.delivery_models import WebhookDelivery
from src.webhooks.models import Webhook
from src.webhooks.signature import verify_webhook_signature


@pytest.fixture(autouse=True)
async def ensure_app_started():
    app.state.startup_complete = True


@pytest.fixture
def session_factory():
    return get_session_maker()


async def _create_community_server(session_factory) -> UUID:
    """Insert a minimal CommunityServer row and return its id."""
    server_id = uuid4()
    async with session_factory() as session:
        await session.execute(
            insert(CommunityServer).values(
                id=server_id,
                platform="discord",
                platform_community_server_id=f"test-guild-{server_id}",
                name="Test Server",
            )
        )
        await session.commit()
    return server_id


async def _create_webhook(
    session_factory,
    community_server_id: UUID,
    url: str = "https://example.com/webhook",
    secret: str = "test-secret-key-for-hmac",
    events: list[str] | None = None,
) -> types.SimpleNamespace:
    """Insert a Webhook row and return a SimpleNamespace with its attributes."""
    webhook_id = uuid4()
    async with session_factory() as session:
        await session.execute(
            insert(Webhook).values(
                id=webhook_id,
                url=url,
                secret=secret,
                community_server_id=community_server_id,
                active=True,
                events=events,
            )
        )
        await session.commit()
    return types.SimpleNamespace(
        id=webhook_id,
        url=url,
        secret=secret,
        community_server_id=community_server_id,
        channel_id=None,
        active=True,
        events=events,
    )


@pytest.mark.asyncio
async def test_registration_requires_auth() -> None:
    """Registration endpoint returns 401 without auth token."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhooks/register",
            json={
                "url": "https://example.com/hook",
                "secret": "s3cr3t",
                "platform_community_server_id": "guild_auth_test",
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_successful_delivery_creates_delivered_record(
    session_factory,
) -> None:
    """Successful HTTP delivery persists WebhookDelivery with status=delivered."""
    community_server_id = await _create_community_server(session_factory)
    webhook = await _create_webhook(session_factory, community_server_id)

    event_id = str(uuid4())
    event_type = "moderation_action.proposed"
    payload = {"action_id": str(uuid4()), "event_type": event_type}

    with (
        patch(
            "src.webhooks.delivery.OutboundWebhookDeliveryService._fetch_active_webhooks",
            new=AsyncMock(return_value=[webhook]),
        ),
        patch.object(
            OutboundWebhookDeliveryService,
            "_attempt_delivery",
            new=AsyncMock(return_value=(True, 200, "")),
        ),
    ):
        service = OutboundWebhookDeliveryService(session_factory)
        await service.deliver_event(event_type, event_id, payload, community_server_id)

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.event_id == event_id,
                WebhookDelivery.webhook_id == webhook.id,
            )
        )
        delivery = result.scalar_one_or_none()

    assert delivery is not None
    assert delivery.status == "delivered"
    assert delivery.attempts == 1
    assert delivery.delivered_at is not None
    assert delivery.last_error is None


@pytest.mark.asyncio
async def test_hmac_signature_in_headers_is_verifiable(
    session_factory,
) -> None:
    """_attempt_delivery sends X-Webhook-Signature and X-Webhook-Timestamp that are verifiable."""
    community_server_id = await _create_community_server(session_factory)
    webhook = await _create_webhook(session_factory, community_server_id)
    payload = {"action_id": str(uuid4()), "event_type": "moderation_action.applied"}

    captured_headers: dict[str, str] = {}

    async def fake_post(url, *, json=None, headers=None, **kwargs):
        if headers:
            captured_headers.update(headers)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.is_success = True
        return resp

    service = OutboundWebhookDeliveryService(session_factory)
    with patch.object(service._client, "post", side_effect=fake_post):
        success, _status_code, _error = await service._attempt_delivery(webhook, payload)

    assert success is True
    assert "X-Webhook-Signature" in captured_headers
    assert "X-Webhook-Timestamp" in captured_headers

    raw_sig = captured_headers["X-Webhook-Signature"]
    assert raw_sig.startswith("sha256="), f"Expected sha256= prefix, got: {raw_sig}"
    hex_sig = raw_sig[len("sha256=") :]

    timestamp = int(captured_headers["X-Webhook-Timestamp"])
    assert abs(timestamp - int(time.time())) < 10

    is_valid = verify_webhook_signature(payload, webhook.secret, timestamp, hex_sig)
    assert is_valid, "Signature could not be verified with the webhook secret"


@pytest.mark.asyncio
async def test_retry_on_500_marks_failed_after_3_attempts(
    session_factory,
) -> None:
    """A 500 response triggers retries; after 3 failures the delivery is marked failed."""
    community_server_id = await _create_community_server(session_factory)
    webhook = await _create_webhook(session_factory, community_server_id)

    event_id = str(uuid4())
    event_type = "moderation_action.proposed"
    payload = {"action_id": str(uuid4())}

    call_count = 0

    async def mock_attempt(self_obj, wh, pl):
        nonlocal call_count
        call_count += 1
        return False, 500, "Internal Server Error"

    with (
        patch(
            "src.webhooks.delivery.OutboundWebhookDeliveryService._fetch_active_webhooks",
            new=AsyncMock(return_value=[webhook]),
        ),
        patch.object(OutboundWebhookDeliveryService, "_attempt_delivery", new=mock_attempt),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        service = OutboundWebhookDeliveryService(session_factory)
        await service.deliver_event(event_type, event_id, payload, community_server_id)

    assert call_count == 3, f"Expected 3 attempts, got {call_count}"

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.event_id == event_id,
                WebhookDelivery.webhook_id == webhook.id,
            )
        )
        delivery = result.scalar_one_or_none()

    assert delivery is not None
    assert delivery.status == "failed"
    assert delivery.attempts == 3
    assert delivery.delivered_at is None
    assert delivery.last_error is not None


@pytest.mark.asyncio
async def test_no_retry_on_400_immediate_fail(
    session_factory,
) -> None:
    """A 4xx response (except 429) causes immediate failure with no retry."""
    community_server_id = await _create_community_server(session_factory)
    webhook = await _create_webhook(session_factory, community_server_id)

    event_id = str(uuid4())
    event_type = "moderation_action.proposed"
    payload = {"action_id": str(uuid4())}

    call_count = 0

    async def mock_attempt(self_obj, wh, pl):
        nonlocal call_count
        call_count += 1
        return False, 400, "Bad Request"

    with (
        patch(
            "src.webhooks.delivery.OutboundWebhookDeliveryService._fetch_active_webhooks",
            new=AsyncMock(return_value=[webhook]),
        ),
        patch.object(OutboundWebhookDeliveryService, "_attempt_delivery", new=mock_attempt),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        service = OutboundWebhookDeliveryService(session_factory)
        await service.deliver_event(event_type, event_id, payload, community_server_id)

    assert call_count == 1, f"Expected 1 attempt (no retry on 400), got {call_count}"

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.event_id == event_id,
                WebhookDelivery.webhook_id == webhook.id,
            )
        )
        delivery = result.scalar_one_or_none()

    assert delivery is not None
    assert delivery.status == "failed"
    assert delivery.attempts == 1


@pytest.mark.asyncio
async def test_events_filter_restricts_delivery(
    session_factory,
) -> None:
    """Webhook with events=['moderation_action.proposed'] does not receive other event types."""
    community_server_id = await _create_community_server(session_factory)
    specific_webhook = await _create_webhook(
        session_factory,
        community_server_id,
        url="https://example.com/specific",
        secret="secret1",
        events=["moderation_action.proposed"],
    )
    wildcard_webhook = await _create_webhook(
        session_factory,
        community_server_id,
        url="https://example.com/all",
        secret="secret2",
        events=None,
    )

    event_id = str(uuid4())
    event_type = "moderation_action.applied"
    payload = {"action_id": str(uuid4())}

    called_urls: list[str] = []

    async def mock_attempt(self_obj, wh, pl):
        called_urls.append(wh.url)
        return True, 200, ""

    with (
        patch(
            "src.webhooks.delivery.OutboundWebhookDeliveryService._fetch_active_webhooks",
            new=AsyncMock(return_value=[specific_webhook, wildcard_webhook]),
        ),
        patch.object(OutboundWebhookDeliveryService, "_attempt_delivery", new=mock_attempt),
    ):
        service = OutboundWebhookDeliveryService(session_factory)
        await service.deliver_event(event_type, event_id, payload, community_server_id)

    assert "https://example.com/specific" not in called_urls, (
        "Webhook filtered to 'moderation_action.proposed' should NOT receive 'moderation_action.applied'"
    )
    assert "https://example.com/all" in called_urls, (
        "Wildcard webhook (events=None) should receive all events"
    )


@pytest.mark.asyncio
async def test_events_filter_allows_matching_event(
    session_factory,
) -> None:
    """Webhook with events=['moderation_action.proposed'] receives that exact event type."""
    community_server_id = await _create_community_server(session_factory)
    specific_webhook = await _create_webhook(
        session_factory,
        community_server_id,
        url="https://example.com/specific",
        secret="secret1",
        events=["moderation_action.proposed"],
    )

    event_id = str(uuid4())
    event_type = "moderation_action.proposed"
    payload = {"action_id": str(uuid4())}

    called_urls: list[str] = []

    async def mock_attempt(self_obj, wh, pl):
        called_urls.append(wh.url)
        return True, 200, ""

    with (
        patch(
            "src.webhooks.delivery.OutboundWebhookDeliveryService._fetch_active_webhooks",
            new=AsyncMock(return_value=[specific_webhook]),
        ),
        patch.object(OutboundWebhookDeliveryService, "_attempt_delivery", new=mock_attempt),
    ):
        service = OutboundWebhookDeliveryService(session_factory)
        await service.deliver_event(event_type, event_id, payload, community_server_id)

    assert "https://example.com/specific" in called_urls, (
        "Webhook filtered to 'moderation_action.proposed' should receive that event type"
    )


@pytest.mark.asyncio
async def test_duplicate_event_does_not_create_second_delivery_row(
    session_factory,
    caplog,
) -> None:
    """TASK-1401.17: duplicate (webhook_id, event_id) is rejected by the unique
    constraint; only one WebhookDelivery row exists per (webhook, event) pair.

    This is the correctness property that lets `publish_moderation_action_applied`
    safely use a deterministic event_id — DBOS step retries re-emit the same
    event_id, and the webhook layer dedupes at flush time instead of producing
    duplicate outbound HTTP POSTs.

    We call `_deliver_to_webhook` directly (not `deliver_event`) because
    `deliver_event` uses `asyncio.gather(return_exceptions=True)` which would
    silently swallow any unhandled exception from the second call and let the
    test pass even if the dedup branch never ran. The log-line assertion plus
    the direct call prove the IntegrityError branch actually fired.
    """
    import logging

    community_server_id = await _create_community_server(session_factory)
    webhook = await _create_webhook(session_factory, community_server_id)

    event_id = str(uuid4())
    event_type = "moderation_action.applied"
    payload = {"action_id": str(uuid4()), "attempt": 1}

    call_count = 0

    async def mock_attempt(self_obj, wh, pl):
        nonlocal call_count
        call_count += 1
        return True, 200, ""

    service = OutboundWebhookDeliveryService(session_factory)
    with patch.object(OutboundWebhookDeliveryService, "_attempt_delivery", new=mock_attempt):
        await service._deliver_to_webhook(webhook, event_type, event_id, payload)
        # Simulate a DBOS retry: same event_id, different payload attempt counter.
        payload_retry = {**payload, "attempt": 2}
        with caplog.at_level(logging.INFO, logger="src.webhooks.delivery"):
            await service._deliver_to_webhook(webhook, event_type, event_id, payload_retry)

    assert call_count == 1, (
        "Second _deliver_to_webhook call must be blocked by the unique constraint — "
        "the duplicate HTTP POST is exactly what TASK-1401.17 prevents."
    )

    # Prove the IntegrityError swallow branch ran, not some earlier short-circuit.
    assert any(
        "already exists" in rec.message and str(webhook.id) in rec.message for rec in caplog.records
    ), (
        "Expected 'Webhook delivery already exists' INFO log on the retry call — "
        "if missing, the test passed for the wrong reason."
    )

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.event_id == event_id,
                WebhookDelivery.webhook_id == webhook.id,
            )
        )
        rows = list(result.scalars().all())

    assert len(rows) == 1, f"Expected exactly one delivery row, got {len(rows)}"
    # The row preserves the first payload — the second attempt was fully rejected.
    assert rows[0].payload == payload


@pytest.mark.asyncio
async def test_non_unique_integrity_error_is_not_swallowed(session_factory) -> None:
    """Review follow-up (Codex High #1): `_deliver_to_webhook` must only swallow
    SQLSTATE 23505 (unique_violation). Other IntegrityError causes (FK violation
    from a concurrently-deleted webhook, check-constraint failures, etc.) must
    propagate so the NATS handler can NAK and retry — otherwise the event is
    silently dropped and the NATS message is ACKed."""
    community_server_id = await _create_community_server(session_factory)
    # Fabricate a webhook row that does NOT exist in the DB. The INSERT will
    # raise IntegrityError with pgcode 23503 (foreign_key_violation), which must
    # propagate to the caller.
    phantom_webhook = types.SimpleNamespace(
        id=uuid4(),
        url="https://example.com/phantom",
        secret="s",
        community_server_id=community_server_id,
        channel_id=None,
        active=True,
        events=None,
    )

    from sqlalchemy.exc import IntegrityError

    service = OutboundWebhookDeliveryService(session_factory)
    with pytest.raises(IntegrityError, match=r"foreign key|violates"):
        await service._deliver_to_webhook(
            phantom_webhook, "moderation_action.applied", str(uuid4()), {"x": 1}
        )
