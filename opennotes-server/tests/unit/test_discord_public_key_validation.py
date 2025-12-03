import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


class TestDiscordPublicKeyPydanticValidation:
    def test_empty_public_key_allowed(self) -> None:
        from src.config import Settings

        settings = Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY="")
        assert settings.DISCORD_PUBLIC_KEY == ""

    def test_valid_64_hex_character_key(self) -> None:
        from src.config import Settings

        valid_key = "a" * 64
        settings = Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY=valid_key)
        assert valid_key == settings.DISCORD_PUBLIC_KEY

    def test_invalid_length_too_short(self) -> None:
        from src.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY="abc123")
        assert "must be exactly 64 hex characters" in str(exc_info.value)

    def test_invalid_length_too_long(self) -> None:
        from src.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY="0" * 128)
        assert "must be exactly 64 hex characters" in str(exc_info.value)

    def test_invalid_hex_characters(self) -> None:
        from src.config import Settings

        invalid_key = "xyz" + "0" * 61
        with pytest.raises(ValidationError) as exc_info:
            Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY=invalid_key)
        assert "must be valid hexadecimal" in str(exc_info.value)

    def test_non_hex_but_correct_length(self) -> None:
        from src.config import Settings

        invalid_key = "g" * 64
        with pytest.raises(ValidationError) as exc_info:
            Settings(JWT_SECRET_KEY="a" * 32, DISCORD_PUBLIC_KEY=invalid_key)
        assert "must be valid hexadecimal" in str(exc_info.value)


class TestDiscordPublicKeyRuntimeValidation:
    def test_empty_public_key_returns_false(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", ""),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is False

    def test_invalid_length_short_returns_false(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", "abc"),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is False

    def test_invalid_length_long_returns_false(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", "0" * 128),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is False

    def test_invalid_hex_format_returns_false(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        invalid_key = "xyz" + "0" * 61
        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", invalid_key),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is False

    def test_test_environment_bypass_still_works(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", ""),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "test"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is True

    def test_development_environment_bypass_still_works(self) -> None:
        from unittest.mock import patch

        from src.webhooks.verification import verify_discord_signature

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", ""),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "development"),
        ):
            result = verify_discord_signature(
                body=b"test",
                signature="0" * 128,
                timestamp="1234567890",
            )
            assert result is True

    def test_valid_public_key_length_check_passes(self) -> None:
        import time
        from unittest.mock import patch

        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )

        from src.webhooks.verification import verify_discord_signature

        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        public_key_hex = public_key.public_bytes_raw().hex()

        body = b"test_body"
        timestamp = str(int(time.time()))
        message = timestamp.encode() + body
        signature = private_key.sign(message).hex()

        with (
            patch("src.webhooks.verification.settings.DISCORD_PUBLIC_KEY", public_key_hex),
            patch("src.webhooks.verification.settings.ENVIRONMENT", "production"),
        ):
            result = verify_discord_signature(
                body=body,
                signature=signature,
                timestamp=timestamp,
            )
            assert result is True
