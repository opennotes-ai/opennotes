"""Unit tests for previously-seen configuration settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings

TEST_CREDENTIALS_ENCRYPTION_KEY = "WSaz4Oan5Rx-0zD-6wC7yOfasrJmzZDVViu6WzwSi0Q="
TEST_ENCRYPTION_MASTER_KEY = "F5UG5HjhMjOgapb3ADail98bpydyrnrFfgkH1YB_zuE="
TEST_JWT_SECRET_KEY = "a" * 32


@pytest.fixture(autouse=True)
def clear_settings_singleton():
    """Clear Settings singleton before each test to avoid state leakage."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def create_settings_no_env_file(**kwargs):
    """Create Settings instance without loading .env file."""
    return Settings(_env_file=None, **kwargs)


class TestPreviouslySeenThresholdDefaults:
    """Test default threshold configuration values."""

    def test_autopublish_threshold_default(self):
        """Test PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD has correct default value."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD == 0.9

    def test_autorequest_threshold_default(self):
        """Test PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD has correct default value."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD == 0.75

    def test_autopublish_threshold_custom_value(self):
        """Test PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD can be customized."""
        custom_threshold = 0.85
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD": str(custom_threshold),
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert custom_threshold == settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD

    def test_autorequest_threshold_custom_value(self):
        """Test PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD can be customized."""
        custom_threshold = 0.65
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD": str(custom_threshold),
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert custom_threshold == settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD


class TestPreviouslySeenThresholdValidation:
    """Test threshold validation constraints."""

    def test_autopublish_threshold_rejects_below_zero(self):
        """Test PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD rejects values below 0.0."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD": "-0.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any("PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD" in str(error) for error in errors)

    def test_autopublish_threshold_rejects_above_one(self):
        """Test PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD rejects values above 1.0."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD": "1.1",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any("PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD" in str(error) for error in errors)

    def test_autorequest_threshold_rejects_below_zero(self):
        """Test PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD rejects values below 0.0."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD": "-0.5",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any("PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD" in str(error) for error in errors)

    def test_autorequest_threshold_rejects_above_one(self):
        """Test PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD rejects values above 1.0."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD": "2.0",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                create_settings_no_env_file()

            errors = exc_info.value.errors()
            assert any("PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD" in str(error) for error in errors)

    def test_both_thresholds_accept_boundary_values(self):
        """Test both thresholds accept valid boundary values (0.0 and 1.0)."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET_KEY": TEST_JWT_SECRET_KEY,
                "ENVIRONMENT": "development",
                "CREDENTIALS_ENCRYPTION_KEY": TEST_CREDENTIALS_ENCRYPTION_KEY,
                "ENCRYPTION_MASTER_KEY": TEST_ENCRYPTION_MASTER_KEY,
                "PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD": "1.0",
                "PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD": "0.0",
            },
            clear=True,
        ):
            settings = create_settings_no_env_file()
            assert settings.PREVIOUSLY_SEEN_AUTOPUBLISH_THRESHOLD == 1.0
            assert settings.PREVIOUSLY_SEEN_AUTOREQUEST_THRESHOLD == 0.0
