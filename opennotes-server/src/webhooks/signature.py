"""
Webhook signature generation and validation using HMAC-SHA256.

Prevents webhook forgery by requiring clients to verify signatures.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_WEBHOOK_AGE_SECONDS = 300


class WebhookSignature(BaseModel):
    """Webhook signature for HMAC validation."""

    timestamp: int = Field(..., ge=0, description="Unix timestamp when webhook was created")
    signature: str = Field(..., min_length=64, max_length=64, description="HMAC-SHA256 signature")


def generate_webhook_signature(
    payload: dict[str, Any],
    secret: str,
    timestamp: int | None = None,
) -> WebhookSignature:
    """
    Generate HMAC signature for a webhook payload.

    Args:
        payload: The webhook payload dict
        secret: The webhook secret key
        timestamp: Optional timestamp (defaults to current time)

    Returns:
        WebhookSignature with timestamp and signature
    """
    if timestamp is None:
        timestamp = int(time.time())

    payload_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    message = f"{timestamp}:{payload_str}"

    signature = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return WebhookSignature(timestamp=timestamp, signature=signature)


def verify_webhook_signature(
    payload: dict[str, Any],
    secret: str,
    timestamp: int,
    provided_signature: str,
) -> bool:
    """
    Verify HMAC signature for a webhook payload.

    Args:
        payload: The webhook payload dict
        secret: The webhook secret key
        timestamp: The timestamp from the webhook
        provided_signature: The signature to verify

    Returns:
        True if signature is valid and timestamp is fresh, False otherwise
    """
    try:
        current_time = int(time.time())
        age = abs(current_time - timestamp)

        if age > MAX_WEBHOOK_AGE_SECONDS:
            logger.warning(
                f"Webhook timestamp too old or from future: age={age}s, max={MAX_WEBHOOK_AGE_SECONDS}s"
            )
            return False

        expected = generate_webhook_signature(payload, secret, timestamp)

        if not hmac.compare_digest(expected.signature, provided_signature):
            logger.warning("Webhook signature verification failed")
            return False

        return True

    except Exception as e:
        logger.error(f"Webhook signature verification error: {e}")
        return False


def add_signature_to_webhook(
    payload: dict[str, Any],
    secret: str,
) -> dict[str, Any]:
    """
    Add signature and timestamp to webhook payload.

    Args:
        payload: The webhook payload dict
        secret: The webhook secret key

    Returns:
        New dict with _webhook_timestamp and _webhook_signature fields added
    """
    sig = generate_webhook_signature(payload, secret)

    return {
        **payload,
        "_webhook_timestamp": sig.timestamp,
        "_webhook_signature": sig.signature,
    }


def extract_and_verify_webhook(
    payload_with_signature: dict[str, Any],
    secret: str,
) -> tuple[dict[str, Any], bool]:
    """
    Extract payload and verify signature from webhook.

    Args:
        payload_with_signature: Webhook payload including _webhook_timestamp and _webhook_signature
        secret: The webhook secret key

    Returns:
        Tuple of (original_payload, is_valid)
    """
    try:
        timestamp = payload_with_signature.get("_webhook_timestamp")
        signature = payload_with_signature.get("_webhook_signature")

        if not timestamp or not signature:
            logger.warning("Webhook missing timestamp or signature fields")
            return {}, False

        payload = {
            k: v
            for k, v in payload_with_signature.items()
            if k not in ("_webhook_timestamp", "_webhook_signature")
        }

        is_valid = verify_webhook_signature(payload, secret, timestamp, signature)

        return payload, is_valid

    except Exception as e:
        logger.error(f"Failed to extract and verify webhook: {e}")
        return {}, False
