import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings

TEST_CREDENTIALS_ENCRYPTION_KEY = "WSaz4Oan5Rx-0zD-6wC7yOfasrJmzZDVViu6WzwSi0Q="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
TEST_INTERNAL_SERVICE_SECRET = "test-internal-service-secret-must-be-32-chars-min"


@pytest.fixture(autouse=True)
def clear_settings_singleton():
    """Clear Settings singleton before each test to avoid state leakage"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_settings_no_env_file(**kwargs):
    return Settings(_env_file=None, **kwargs)


class TestJWTSecretKeyValidation:
    def test_jwt_secret_key_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["type"] == "missing" and "JWT_SECRET_KEY" in str(error) for error in errors
            )

    def test_jwt_secret_key_minimum_length(self):
        short_key = "short"
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": short_key,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["type"] == "string_too_short" and error["loc"] == ("JWT_SECRET_KEY",)
                for error in errors
            )

    def test_jwt_secret_key_valid_development(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert valid_key == settings.JWT_SECRET_KEY

    def test_jwt_secret_key_valid_production(self):
        valid_key = "x" * 40
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "INTERNAL_SERVICE_SECRET": TEST_INTERNAL_SERVICE_SECRET,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert valid_key == settings.JWT_SECRET_KEY

    def test_production_rejects_placeholder_values(self):
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "dev-secret-key-change-in-production",
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            with pytest.raises((ValueError, ValidationError)) as exc_info:
                create_settings_no_env_file()

            assert "placeholder value" in str(exc_info.value).lower()

    def test_production_rejects_short_placeholder_values(self):
        short_placeholders = ["change-me", "secret", "your-secret-key"]

        for placeholder in short_placeholders:
            with patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": placeholder,
                    "ENVIRONMENT": "production",
                    "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                    "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                },
                clear=True,
            ):
                with pytest.raises(ValidationError) as exc_info:
                    create_settings_no_env_file()

                assert "at least 32 characters" in str(exc_info.value).lower()

    def test_production_requires_minimum_length(self):
        short_key = "short"
        with (
            patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": short_key,
                    "ENVIRONMENT": "production",
                    "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                    "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                },
                clear=True,
            ),
            pytest.raises((ValidationError, ValueError)),
        ):
            create_settings_no_env_file()

    def test_development_allows_placeholder(self):
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "dev-secret-key-change-in-production-min-32-chars",
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.JWT_SECRET_KEY == "dev-secret-key-change-in-production-min-32-chars"

    def test_staging_allows_placeholder(self):
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": "dev-secret-key-change-in-production-min-32-chars",
                "ENVIRONMENT": "staging",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.JWT_SECRET_KEY == "dev-secret-key-change-in-production-min-32-chars"


class TestConfigurationDefaults:
    def test_environment_defaults_to_development(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.ENVIRONMENT == "development"

    def test_debug_defaults_to_false(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.DEBUG is False

    def test_is_development_property(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.is_development is True

        get_settings.cache_clear()

        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "INTERNAL_SERVICE_SECRET": TEST_INTERNAL_SERVICE_SECRET,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.is_development is False


class TestDebugConfiguration:
    def test_debug_can_be_enabled_in_development(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "DEBUG": "true",
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.DEBUG is True

    def test_debug_can_be_enabled_in_staging(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "DEBUG": "true",
                "ENVIRONMENT": "staging",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.DEBUG is True

    def test_debug_blocked_in_production(self):
        valid_key = "x" * 40
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "DEBUG": "true",
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="DEBUG must be False in production") as exc_info:
                create_settings_no_env_file()

            assert "DEBUG must be False in production" in str(exc_info.value)

    def test_debug_false_allowed_in_production(self):
        valid_key = "x" * 40
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "DEBUG": "false",
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "INTERNAL_SERVICE_SECRET": TEST_INTERNAL_SERVICE_SECRET,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.DEBUG is False


class TestOTLPConfiguration:
    def test_otlp_insecure_defaults_to_false(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.OTLP_INSECURE is False

    def test_otlp_insecure_can_be_enabled_for_development(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "OTLP_INSECURE": "true",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.OTLP_INSECURE is True

    def test_otlp_insecure_respects_false_value(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "OTLP_INSECURE": "false",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.OTLP_INSECURE is False

    def test_production_defaults_to_secure_otlp(self):
        valid_key = "x" * 40
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "ENVIRONMENT": "production",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "INTERNAL_SERVICE_SECRET": TEST_INTERNAL_SERVICE_SECRET,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.OTLP_INSECURE is False


class TestCacheLlmPricingTtl:
    def test_cache_llm_pricing_ttl_exists_with_default(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert hasattr(settings, "CACHE_LLM_PRICING_TTL")
            assert settings.CACHE_LLM_PRICING_TTL == 86400

    def test_cache_llm_pricing_ttl_can_be_configured(self):
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "CACHE_LLM_PRICING_TTL": "3600",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.CACHE_LLM_PRICING_TTL == 3600


class TestSettingsSingleton:
    def test_settings_is_singleton(self):
        get_settings.cache_clear()
        settings1 = Settings()
        settings2 = Settings()
        assert settings1 is settings2
        assert id(settings1) == id(settings2)

    def test_get_settings_returns_singleton(self):
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
        assert id(settings1) == id(settings2)

    def test_settings_persists_across_multiple_calls(self):
        get_settings.cache_clear()
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "NATS_URL": "nats://test-host:4222",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings1 = Settings()
            original_nats_url = settings1.NATS_URL

            settings2 = get_settings()
            assert original_nats_url == settings2.NATS_URL

            settings3 = Settings()
            assert original_nats_url == settings3.NATS_URL

            assert id(settings1) == id(settings2) == id(settings3)

    def test_settings_updates_visible_across_instances(self):
        get_settings.cache_clear()
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "NATS_URL": "nats://original-host:4222",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings1 = get_settings()
            assert settings1.NATS_URL == "nats://original-host:4222"

            settings1.NATS_URL = "nats://updated-host:4222"

            settings2 = get_settings()
            assert settings2.NATS_URL == "nats://updated-host:4222"
            assert id(settings1) == id(settings2)

    def test_cache_clear_creates_new_instance(self):
        get_settings.cache_clear()
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "NATS_URL": "nats://host1:4222",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings1 = get_settings()
            assert settings1.NATS_URL == "nats://host1:4222"
            id1 = id(settings1)

            get_settings.cache_clear()

            with patch.dict(
                os.environ,
                {
                    "JWT_SECRET_KEY": valid_key,
                    "NATS_URL": "nats://host2:4222",
                    "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                    "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                },
                clear=True,
            ):
                settings2 = get_settings()
                assert settings2.NATS_URL == "nats://host2:4222"
                id2 = id(settings2)

                assert id1 != id2
