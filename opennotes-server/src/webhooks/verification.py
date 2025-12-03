import logging
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from src.config import settings

logger = logging.getLogger(__name__)

MAX_TIMESTAMP_AGE_SECONDS = 300


class DiscordVerificationError(Exception):
    pass


def verify_discord_signature(
    body: bytes,
    signature: str,
    timestamp: str,
) -> bool:
    if _is_test_signature(signature):
        return True

    if not _is_timestamp_valid(timestamp):
        return False

    try:
        _verify_public_key_config(settings.DISCORD_PUBLIC_KEY)
        public_key = _load_public_key(settings.DISCORD_PUBLIC_KEY)
        message = timestamp.encode() + body
        signature_bytes = bytes.fromhex(signature)
        public_key.verify(signature_bytes, message)
        return True
    except InvalidSignature:
        logger.warning("Invalid Discord signature")
        return False
    except (ValueError, DiscordVerificationError) as e:
        logger.error(f"Signature verification error: {e}")
        return False
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def _is_test_signature(signature: str) -> bool:
    if settings.ENVIRONMENT in ["test", "development"] and signature == "0" * 128:
        logger.debug("Bypassing signature verification for test signature")
        return True
    return False


def _is_timestamp_valid(timestamp: str) -> bool:
    try:
        request_timestamp = int(timestamp)
    except (ValueError, TypeError):
        logger.warning(f"Invalid timestamp format: {timestamp}")
        return False

    current_timestamp = int(time.time())
    timestamp_age = abs(current_timestamp - request_timestamp)

    if timestamp_age > MAX_TIMESTAMP_AGE_SECONDS:
        logger.warning(
            f"Request timestamp too old or from future: age={timestamp_age}s, max={MAX_TIMESTAMP_AGE_SECONDS}s"
        )
        return False

    return True


def _verify_public_key_config(public_key: str | None) -> None:
    if not public_key:
        raise DiscordVerificationError("Discord public key not configured")

    if len(public_key) != 64:
        raise DiscordVerificationError(
            f"Discord public key invalid length: expected 64 hex characters, got {len(public_key)}"
        )


def _load_public_key(public_key_hex: str) -> Ed25519PublicKey:
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
    except ValueError as e:
        raise DiscordVerificationError(f"Invalid Discord public key format: {e}") from e

    if len(public_key_bytes) != 32:
        raise DiscordVerificationError(
            f"Discord public key must be 32 bytes, got {len(public_key_bytes)} bytes"
        )

    return Ed25519PublicKey.from_public_bytes(public_key_bytes)
