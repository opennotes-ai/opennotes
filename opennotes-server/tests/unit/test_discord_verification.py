import time
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.webhooks.verification import (
    MAX_TIMESTAMP_AGE_SECONDS,
    verify_discord_signature,
)


@pytest.fixture
def test_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


@pytest.fixture
def test_public_key(test_private_key: Ed25519PrivateKey) -> str:
    public_key = test_private_key.public_key()
    return public_key.public_bytes_raw().hex()


def create_signature(
    private_key: Ed25519PrivateKey,
    body: bytes,
    timestamp: str,
) -> str:
    message = timestamp.encode() + body
    signature = private_key.sign(message)
    return signature.hex()


def test_valid_signature_and_timestamp(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
) -> None:
    body = b'{"type": 1}'
    timestamp = str(int(time.time()))
    signature = create_signature(test_private_key, body, timestamp)

    with (
        patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
    ):
        result = verify_discord_signature(body, signature, timestamp)
        assert result is True


def test_expired_timestamp(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
) -> None:
    with (
        patch("src.config.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.config.settings.ENVIRONMENT", "production"),
    ):
        body = b'{"type": 1}'
        old_timestamp = str(int(time.time()) - MAX_TIMESTAMP_AGE_SECONDS - 10)
        signature = create_signature(test_private_key, body, old_timestamp)

        result = verify_discord_signature(body, signature, old_timestamp)
        assert result is False


def test_future_timestamp(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
) -> None:
    with (
        patch("src.config.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.config.settings.ENVIRONMENT", "production"),
    ):
        body = b'{"type": 1}'
        future_timestamp = str(int(time.time()) + MAX_TIMESTAMP_AGE_SECONDS + 10)
        signature = create_signature(test_private_key, body, future_timestamp)

        result = verify_discord_signature(body, signature, future_timestamp)
        assert result is False


def test_invalid_timestamp_format(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
) -> None:
    with (
        patch("src.config.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.config.settings.ENVIRONMENT", "production"),
    ):
        body = b'{"type": 1}'
        invalid_timestamp = "not_a_number"
        signature = create_signature(test_private_key, body, invalid_timestamp)

        result = verify_discord_signature(body, signature, invalid_timestamp)
        assert result is False


def test_timestamp_at_boundary(
    test_private_key: Ed25519PrivateKey,
    test_public_key: str,
) -> None:
    body = b'{"type": 1}'
    boundary_timestamp = str(int(time.time()) - MAX_TIMESTAMP_AGE_SECONDS)
    signature = create_signature(test_private_key, body, boundary_timestamp)

    with (
        patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
    ):
        result = verify_discord_signature(body, signature, boundary_timestamp)
        assert result is True


def test_test_environment_bypass() -> None:
    body = b'{"type": 1}'
    timestamp = str(int(time.time()))
    test_signature = "0" * 128

    with patch("src.webhooks.verification.settings.ENVIRONMENT", "test"):
        result = verify_discord_signature(body, test_signature, timestamp)
        assert result is True


def test_invalid_signature_with_valid_timestamp(
    test_public_key: str,
) -> None:
    body = b'{"type": 1}'
    timestamp = str(int(time.time()))
    invalid_signature = "0" * 128

    with (
        patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", test_public_key),
        patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
    ):
        result = verify_discord_signature(body, invalid_signature, timestamp)
        assert result is False
