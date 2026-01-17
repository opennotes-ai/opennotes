import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.cache.redis_client import get_redis_connection_kwargs


class TestRedisTLSConfiguration:
    """Tests for Redis TLS configuration."""

    def test_requires_tls_in_production(self) -> None:
        """Production environment requires TLS (rediss://) URLs."""
        with (
            patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
            patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
            pytest.raises(ValueError, match="must use TLS in production"),
        ):
            get_redis_connection_kwargs("redis://localhost:6379")

    def test_allows_non_tls_in_development(self) -> None:
        """Development environment allows non-TLS URLs."""
        with (
            patch("src.cache.redis_client.settings.ENVIRONMENT", "development"),
            patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
        ):
            kwargs = get_redis_connection_kwargs("redis://localhost:6379")
            assert "ssl_context" not in kwargs

    def test_tls_requires_ca_cert_path(self) -> None:
        """TLS connections require REDIS_CA_CERT_PATH to be set."""
        with (
            patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
            patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
            patch("src.cache.redis_client.settings.REDIS_CA_CERT_PATH", None),
            pytest.raises(ValueError, match="REDIS_CA_CERT_PATH must be set"),
        ):
            get_redis_connection_kwargs("rediss://secure-redis:6380")

    def test_tls_validates_ca_cert_exists(self) -> None:
        """TLS connections validate that CA cert file exists."""
        with (
            patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
            patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
            patch(
                "src.cache.redis_client.settings.REDIS_CA_CERT_PATH",
                "/nonexistent/ca.crt",
            ),
            pytest.raises(ValueError, match="CA certificate not found"),
        ):
            get_redis_connection_kwargs("rediss://secure-redis:6380")

    def test_tls_configures_ssl_context_with_ca_cert(self) -> None:
        """TLS connections configure SSL context with CA certificate."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False) as ca_file:
            ca_file.write("placeholder")
            ca_path = ca_file.name

        try:
            mock_ssl_context = object()
            with (
                patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
                patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", True),
                patch("src.cache.redis_client.settings.REDIS_CA_CERT_PATH", ca_path),
                patch(
                    "src.cache.redis_client.ssl.create_default_context",
                    return_value=mock_ssl_context,
                ) as mock_create_ctx,
            ):
                kwargs = get_redis_connection_kwargs("rediss://secure-redis:6380")
                assert kwargs["ssl_context"] is mock_ssl_context
                mock_create_ctx.assert_called_once_with(cafile=ca_path)
        finally:
            Path(ca_path).unlink()

    def test_can_disable_tls_requirement_in_production(self) -> None:
        """REDIS_REQUIRE_TLS=false allows non-TLS in production."""
        with (
            patch("src.cache.redis_client.settings.ENVIRONMENT", "production"),
            patch("src.cache.redis_client.settings.REDIS_REQUIRE_TLS", False),
        ):
            kwargs = get_redis_connection_kwargs("redis://localhost:6379")
            assert "ssl_context" not in kwargs
