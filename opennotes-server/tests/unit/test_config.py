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


class TestSkipStartupChecksValidation:
    """Test SKIP_STARTUP_CHECKS config parsing (task-922)."""

    def test_skip_startup_checks_empty_default(self):
        """Empty default should return empty list."""
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
            assert settings.SKIP_STARTUP_CHECKS == []

    def test_skip_startup_checks_comma_separated(self):
        """Comma-separated format should be parsed correctly."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": "database_schema,postgresql,redis",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["database_schema", "postgresql", "redis"]

    def test_skip_startup_checks_json_array(self):
        """Valid JSON array format should be parsed correctly."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": '["database_schema", "postgresql"]',
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["database_schema", "postgresql"]

    def test_skip_startup_checks_bracket_notation_unquoted(self):
        """Bracket notation with unquoted values like '[all]' should work."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": "[all]",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["all"]

    def test_skip_startup_checks_bracket_notation_multiple_unquoted(self):
        """Bracket notation with multiple unquoted values like '[a, b, c]'."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": "[database_schema, redis, nats]",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["database_schema", "redis", "nats"]

    def test_skip_startup_checks_single_value(self):
        """Single value without brackets or commas should work."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": "database_schema",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["database_schema"]

    def test_skip_startup_checks_strips_whitespace(self):
        """Whitespace should be stripped from values."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "SKIP_STARTUP_CHECKS": "  database_schema , postgresql  ",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.SKIP_STARTUP_CHECKS == ["database_schema", "postgresql"]


class TestBulkContentScanRepromptDaysValidation:
    """Test BULK_CONTENT_SCAN_REPROMPT_DAYS config validation (task-849.18)."""

    def test_bulk_content_scan_reprompt_days_default_value(self):
        """Default value should be 90 days."""
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
            assert settings.BULK_CONTENT_SCAN_REPROMPT_DAYS == 90

    def test_bulk_content_scan_reprompt_days_rejects_zero(self):
        """Value of 0 should be rejected (ge=1)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "0",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("BULK_CONTENT_SCAN_REPROMPT_DAYS",)
                and "greater than or equal to 1" in str(error["msg"]).lower()
                for error in errors
            ), f"Expected validation error for ge=1, got: {errors}"

    def test_bulk_content_scan_reprompt_days_rejects_negative(self):
        """Negative values should be rejected (ge=1)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "-10",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(error["loc"] == ("BULK_CONTENT_SCAN_REPROMPT_DAYS",) for error in errors), (
                f"Expected validation error for negative value, got: {errors}"
            )

    def test_bulk_content_scan_reprompt_days_rejects_over_365(self):
        """Values over 365 should be rejected (le=365)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "366",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("BULK_CONTENT_SCAN_REPROMPT_DAYS",)
                and "less than or equal to 365" in str(error["msg"]).lower()
                for error in errors
            ), f"Expected validation error for le=365, got: {errors}"

    def test_bulk_content_scan_reprompt_days_rejects_large_value(self):
        """Very large values should be rejected (le=365)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "1000",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(error["loc"] == ("BULK_CONTENT_SCAN_REPROMPT_DAYS",) for error in errors), (
                f"Expected validation error for value over 365, got: {errors}"
            )

    def test_bulk_content_scan_reprompt_days_accepts_minimum_boundary(self):
        """Value of 1 should be accepted (boundary test for ge=1)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "1",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.BULK_CONTENT_SCAN_REPROMPT_DAYS == 1

    def test_bulk_content_scan_reprompt_days_accepts_maximum_boundary(self):
        """Value of 365 should be accepted (boundary test for le=365)."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "365",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.BULK_CONTENT_SCAN_REPROMPT_DAYS == 365

    def test_bulk_content_scan_reprompt_days_accepts_mid_range(self):
        """Mid-range values should be accepted."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "BULK_CONTENT_SCAN_REPROMPT_DAYS": "180",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.BULK_CONTENT_SCAN_REPROMPT_DAYS == 180


class TestLLMModelNameValidation:
    """Test LLM model name validation to prevent empty strings (task-974)."""

    def test_relevance_check_model_rejects_empty_string(self):
        """RELEVANCE_CHECK_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "RELEVANCE_CHECK_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("RELEVANCE_CHECK_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_default_full_model_rejects_empty_string(self):
        """DEFAULT_FULL_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "DEFAULT_FULL_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("DEFAULT_FULL_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_default_mini_model_rejects_empty_string(self):
        """DEFAULT_MINI_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "DEFAULT_MINI_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("DEFAULT_MINI_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_embedding_model_rejects_empty_string(self):
        """EMBEDDING_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "EMBEDDING_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("EMBEDDING_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_vision_model_rejects_empty_string(self):
        """VISION_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "VISION_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("VISION_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_ai_note_writer_model_rejects_empty_string(self):
        """AI_NOTE_WRITER_MODEL cannot be empty string."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "AI_NOTE_WRITER_MODEL": "",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any(
                error["loc"] == ("AI_NOTE_WRITER_MODEL",)
                and "string_too_short" in str(error["type"]).lower()
                for error in errors
            ), f"Expected min_length validation error, got: {errors}"

    def test_model_names_have_valid_defaults(self):
        """All model name fields should have valid non-empty defaults."""
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
            assert settings.RELEVANCE_CHECK_MODEL == "openai/gpt-5-mini"
            assert settings.DEFAULT_FULL_MODEL == "openai/gpt-5.1"
            assert settings.DEFAULT_MINI_MODEL == "openai/gpt-5-mini"
            assert settings.EMBEDDING_MODEL == "text-embedding-3-small"
            assert settings.VISION_MODEL == "openai/gpt-5.1"
            assert settings.AI_NOTE_WRITER_MODEL == "openai/gpt-5.1"


class TestNATSServersConfiguration:
    """Test NATS_SERVERS config parsing for cluster failover (task-1038)."""

    def test_nats_servers_falls_back_to_nats_url_when_not_set(self):
        """When NATS_SERVERS is not set, should fall back to NATS_URL."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_URL": "nats://single-server:4222",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == ["nats://single-server:4222"]

    def test_nats_servers_falls_back_to_default_when_neither_set(self):
        """When neither NATS_SERVERS nor NATS_URL is set, use default."""
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
            assert settings.NATS_SERVERS == ["nats://localhost:4222"]

    def test_nats_servers_parses_comma_separated_urls(self):
        """NATS_SERVERS with comma-separated URLs should be parsed into list."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_SERVERS": "nats://10.0.0.1:4222,nats://10.0.0.2:4222,nats://10.0.0.3:4222",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == [
                "nats://10.0.0.1:4222",
                "nats://10.0.0.2:4222",
                "nats://10.0.0.3:4222",
            ]

    def test_nats_servers_strips_whitespace_from_urls(self):
        """Whitespace around URLs should be stripped."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_SERVERS": "  nats://10.0.0.1:4222 , nats://10.0.0.2:4222  ",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == [
                "nats://10.0.0.1:4222",
                "nats://10.0.0.2:4222",
            ]

    def test_nats_servers_ignores_empty_values(self):
        """Empty values in comma-separated list should be ignored."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_SERVERS": "nats://10.0.0.1:4222,,nats://10.0.0.2:4222,",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == [
                "nats://10.0.0.1:4222",
                "nats://10.0.0.2:4222",
            ]

    def test_nats_servers_single_url(self):
        """Single URL in NATS_SERVERS should work."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_SERVERS": "nats://cluster-node:4222",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == ["nats://cluster-node:4222"]

    def test_nats_servers_overrides_nats_url(self):
        """When NATS_SERVERS is set, it should take precedence over NATS_URL."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_URL": "nats://ignored:4222",
                "NATS_SERVERS": "nats://used:4222",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == ["nats://used:4222"]

    def test_nats_servers_empty_string_falls_back_to_nats_url(self):
        """Empty NATS_SERVERS should fall back to NATS_URL."""
        valid_key = "a" * 32
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": valid_key,
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "NATS_URL": "nats://fallback:4222",
                "NATS_SERVERS": "",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.NATS_SERVERS == ["nats://fallback:4222"]
