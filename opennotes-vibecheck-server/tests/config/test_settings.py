import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


def test_defaults():
    s = Settings()
    assert s.VERTEXAI_FAST_MODEL == "google-vertex:gemini-3-flash-preview"
    assert s.VERTEXAI_MODEL == "google-vertex:gemini-3.1-pro-preview"
    assert s.VERTEX_MAX_CONCURRENCY == 4
    assert s.VIBECHECK_MAX_INSTANCES == 1
    assert s.VIBECHECK_LIMITER_REDIS_URL == ""
    assert s.VIBECHECK_LIMITER_REDIS_CA_CERT_PATH == ""
    assert s.VIBECHECK_LIMITER_KEY_SALT == ""
    assert s.VERTEX_LEASE_ACQUIRE_TIMEOUT_MS == 30_000
    assert s.VERTEX_LEASE_TTL_MS == 300_000
    assert s.MAX_IMAGES_MODERATED == 30
    assert s.MAX_VIDEOS_MODERATED == 5
    assert s.WEB_RISK_CACHE_TTL_HOURS == 6
    assert s.VIBECHECK_SCRAPE_API_TOKEN == ""
    assert s.VIBECHECK_WEB_URL == ""


def test_max_images_moderated_env_override(monkeypatch):
    monkeypatch.setenv("MAX_IMAGES_MODERATED", "50")
    get_settings.cache_clear()
    try:
        assert get_settings().MAX_IMAGES_MODERATED == 50
    finally:
        get_settings.cache_clear()


def test_max_videos_moderated_env_override(monkeypatch):
    monkeypatch.setenv("MAX_VIDEOS_MODERATED", "20")
    get_settings.cache_clear()
    try:
        assert get_settings().MAX_VIDEOS_MODERATED == 20
    finally:
        get_settings.cache_clear()


def test_web_risk_cache_ttl_env_override(monkeypatch):
    monkeypatch.setenv("WEB_RISK_CACHE_TTL_HOURS", "12")
    get_settings.cache_clear()
    try:
        assert get_settings().WEB_RISK_CACHE_TTL_HOURS == 12
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "environment",
    ["development", "staging", "test"],
)
def test_nonproduction_does_not_require_limiter_redis_auth(environment: str):
    Settings(
        ENVIRONMENT=environment,
        VIBECHECK_LIMITER_REDIS_URL="",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="",
        VIBECHECK_LIMITER_KEY_SALT="",
    )


def test_production_requires_dedicated_limiter_redis_url():
    with pytest.raises(ValueError, match="VIBECHECK_LIMITER_REDIS_URL"):
        Settings(ENVIRONMENT="production")


def test_production_limiter_redis_requires_tls_and_ca_path():
    assert Settings(
        ENVIRONMENT="production",
        VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VIBECHECK_LIMITER_KEY_SALT="a" * 64,
    )
    assert Settings(
        ENVIRONMENT="production",
        VIBECHECK_LIMITER_REDIS_URL="rediss://redis-user:secret@10.0.0.1:6379",
        VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
        VIBECHECK_LIMITER_KEY_SALT="a" * 64,
    )

    with pytest.raises(ValueError, match="rediss://"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="redis://:secret@10.0.0.1:6379",
            VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
            VIBECHECK_LIMITER_KEY_SALT="a" * 64,
        )

    with pytest.raises(ValueError, match="VIBECHECK_LIMITER_REDIS_CA_CERT_PATH"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
        )

    with pytest.raises(ValueError, match="AUTH password"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="rediss://10.0.0.1:6379",
            VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
            VIBECHECK_LIMITER_KEY_SALT="a" * 64,
        )

    with pytest.raises(ValueError, match="AUTH password"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="rediss://alice@10.0.0.1:6379",
            VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
            VIBECHECK_LIMITER_KEY_SALT="a" * 64,
        )

    with pytest.raises(ValueError, match="cannot be empty"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="rediss://:@10.0.0.1:6379",
            VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
            VIBECHECK_LIMITER_KEY_SALT="a" * 64,
        )


def test_production_limiter_redis_requires_key_salt():
    with pytest.raises(ValueError, match="VIBECHECK_LIMITER_KEY_SALT"):
        Settings(
            ENVIRONMENT="production",
            VIBECHECK_LIMITER_REDIS_URL="rediss://:secret@10.0.0.1:6379",
            VIBECHECK_LIMITER_REDIS_CA_CERT_PATH="/etc/ssl/vibecheck-limiter-redis/ca.crt",
            VIBECHECK_LIMITER_KEY_SALT="",
        )


def test_vibec_max_instances_env_override(monkeypatch):
    monkeypatch.setenv("VIBECHECK_MAX_INSTANCES", "5")
    get_settings.cache_clear()
    try:
        assert get_settings().VIBECHECK_MAX_INSTANCES == 5
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("value", [0, -3])
def test_vibec_max_instances_rejects_non_positive(value: int):
    with pytest.raises(ValidationError, match="Vertex limiter numeric settings must be > 0"):
        Settings(VIBECHECK_MAX_INSTANCES=value)
