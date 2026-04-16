import asyncio
import logging
from uuid import UUID

import httpx
import pendulum
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.webhooks.delivery_models import WebhookDelivery
from src.webhooks.models import Webhook
from src.webhooks.signature import generate_webhook_signature

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (10, 30, 90)
_MAX_ATTEMPTS = len(_RETRY_DELAYS)


def _should_retry(status_code: int) -> bool:
    return not (400 <= status_code < 500 and status_code != 429)


class OutboundWebhookDeliveryService:
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory
        self._client = httpx.AsyncClient(timeout=5.0)

    async def _fetch_active_webhooks(self, community_server_id: UUID) -> list[Webhook]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(Webhook).where(
                    Webhook.community_server_id == community_server_id,
                    Webhook.active == True,
                )
            )
            return list(result.scalars().all())

    def _webhook_matches_event(self, webhook: Webhook, event_type: str) -> bool:
        if webhook.events is None:
            return True
        return event_type in webhook.events

    async def deliver_event(
        self,
        event_type: str,
        event_id: str,
        payload: dict,
        community_server_id: UUID,
    ) -> None:
        webhooks = await self._fetch_active_webhooks(community_server_id)
        matching = [w for w in webhooks if self._webhook_matches_event(w, event_type)]

        if not matching:
            logger.debug(
                f"No active webhooks match event_type={event_type} for "
                f"community_server_id={community_server_id}"
            )
            return

        tasks = [
            self._deliver_to_webhook(webhook, event_type, event_id, payload) for webhook in matching
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_to_webhook(
        self,
        webhook: Webhook,
        event_type: str,
        event_id: str,
        payload: dict,
    ) -> None:
        try:
            async with self._session_factory() as session:
                delivery = WebhookDelivery(
                    webhook_id=webhook.id,
                    event_type=event_type,
                    event_id=event_id,
                    payload=payload,
                    status="pending",
                    attempts=0,
                )
                session.add(delivery)
                try:
                    await session.flush()
                except IntegrityError as exc:
                    await session.rollback()
                    # Scope the swallow to the unique (webhook_id, event_id) guard.
                    # PostgreSQL SQLSTATE 23505 = unique_violation. Any other
                    # integrity failure (FK violation from a concurrently-deleted
                    # webhook, check constraint, etc.) must propagate so the NATS
                    # handler can NAK and retry instead of silently dropping the event.
                    pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
                    if pgcode != "23505":
                        raise
                    logger.info(
                        "Webhook delivery already exists for (webhook_id=%s, event_id=%s); "
                        "skipping duplicate emit.",
                        webhook.id,
                        event_id,
                    )
                    return

                await self._retry_with_backoff(session, webhook, delivery, payload)
                await session.commit()
        except Exception as exc:
            logger.error(
                f"Unhandled error in _deliver_to_webhook for webhook_id={webhook.id}: {exc}",
                exc_info=True,
            )
            raise

    async def _attempt_delivery(self, webhook: Webhook, payload: dict) -> tuple[bool, int, str]:
        sig = generate_webhook_signature(payload, webhook.secret)
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": f"sha256={sig.signature}",
            "X-Webhook-Timestamp": str(sig.timestamp),
        }

        try:
            response = await self._client.post(webhook.url, json=payload, headers=headers)
            success = response.is_success
            return success, response.status_code, ""
        except Exception as exc:
            logger.warning(f"HTTP request to {webhook.url} failed: {exc}")
            return False, 0, str(exc)

    async def _retry_with_backoff(
        self,
        _session,
        webhook: Webhook,
        delivery: WebhookDelivery,
        payload: dict,
    ) -> None:
        attempt = 0
        last_status_code = 0
        last_error = ""

        while attempt < _MAX_ATTEMPTS:
            if attempt > 0:
                delay = _RETRY_DELAYS[attempt - 1]
                logger.info(
                    f"Webhook delivery retry {attempt}/{_MAX_ATTEMPTS - 1} for "
                    f"delivery webhook_id={delivery.webhook_id} after {delay}s"
                )
                await asyncio.sleep(delay)

            success, status_code, error = await self._attempt_delivery(webhook, payload)
            attempt += 1
            now = pendulum.now("UTC")

            if success:
                delivery.status = "delivered"
                delivery.attempts = attempt
                delivery.last_attempt_at = now
                delivery.last_error = None
                delivery.delivered_at = now
                delivery.updated_at = now
                logger.info(f"Webhook delivered successfully for webhook_id={delivery.webhook_id}")
                return

            last_error = error or f"HTTP {status_code}"
            last_status_code = status_code

            if not _should_retry(status_code):
                logger.warning(
                    f"Webhook delivery failed with non-retryable status {status_code} "
                    f"for webhook_id={delivery.webhook_id}"
                )
                delivery.status = "failed"
                delivery.attempts = attempt
                delivery.last_attempt_at = now
                delivery.last_error = last_error
                delivery.updated_at = now
                return

        logger.error(
            f"Webhook delivery exhausted {_MAX_ATTEMPTS} attempts "
            f"for webhook_id={delivery.webhook_id}, last_status={last_status_code}"
        )
        delivery.status = "failed"
        delivery.attempts = attempt
        delivery.last_attempt_at = pendulum.now("UTC")
        delivery.last_error = last_error
        delivery.updated_at = pendulum.now("UTC")

    async def close(self) -> None:
        await self._client.aclose()
