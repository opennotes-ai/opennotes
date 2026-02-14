"""
Unit tests for encryption key rotation automation.

Tests the KeyRotationManager which provides:
- Automated key rotation scheduling
- Audit trail logging for rotation events
- Alerting when keys exceed configured age thresholds
"""

from unittest.mock import patch

import pendulum
import pytest

pytestmark = pytest.mark.unit


class TestKeyRotationAuditTrail:
    """Tests for audit trail functionality in key rotation."""

    def test_rotation_event_is_logged(self):
        """Rotation events should be recorded in the audit trail."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()
        old_key_id = "v1:abc123"
        new_key_id = "v1:def456"
        config_id = "config-uuid-123"

        manager.record_rotation_event(
            config_id=config_id,
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            reason="scheduled",
        )

        events = manager.get_rotation_history(config_id)
        assert len(events) == 1
        assert events[0]["old_key_id"] == old_key_id
        assert events[0]["new_key_id"] == new_key_id
        assert events[0]["reason"] == "scheduled"
        assert "timestamp" in events[0]

    def test_audit_trail_includes_timestamp(self):
        """Audit trail entries should have accurate timestamps."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()
        before = pendulum.now("UTC")

        manager.record_rotation_event(
            config_id="config-1",
            old_key_id="v1:old",
            new_key_id="v1:new",
            reason="manual",
        )

        after = pendulum.now("UTC")
        events = manager.get_rotation_history("config-1")
        event_time = pendulum.parse(events[0]["timestamp"])

        assert before <= event_time <= after

    def test_audit_trail_preserves_multiple_events(self):
        """Multiple rotation events should all be preserved."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()
        config_id = "config-1"

        for i in range(5):
            manager.record_rotation_event(
                config_id=config_id,
                old_key_id=f"v1:key{i}",
                new_key_id=f"v1:key{i + 1}",
                reason="scheduled",
            )

        events = manager.get_rotation_history(config_id)
        assert len(events) == 5

    def test_audit_trail_isolated_by_config(self):
        """Audit trails should be isolated per config."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()

        manager.record_rotation_event(
            config_id="config-1",
            old_key_id="v1:a",
            new_key_id="v1:b",
            reason="scheduled",
        )
        manager.record_rotation_event(
            config_id="config-2",
            old_key_id="v1:x",
            new_key_id="v1:y",
            reason="manual",
        )

        events_1 = manager.get_rotation_history("config-1")
        events_2 = manager.get_rotation_history("config-2")

        assert len(events_1) == 1
        assert len(events_2) == 1
        assert events_1[0]["old_key_id"] == "v1:a"
        assert events_2[0]["old_key_id"] == "v1:x"


class TestKeyAgeAlerting:
    """Tests for alerting when keys exceed age thresholds."""

    def test_alert_triggered_for_old_keys(self):
        """Alert should be triggered when key exceeds configured age."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            max_key_age_days=30,
        )
        config_id = "config-1"
        old_timestamp = pendulum.now("UTC") - pendulum.duration(days=31)

        manager.register_key(
            config_id=config_id,
            key_id="v1:oldkey",
            created_at=old_timestamp,
        )

        alerts = manager.check_key_age_alerts()
        assert len(alerts) == 1
        assert alerts[0]["config_id"] == config_id
        assert alerts[0]["key_id"] == "v1:oldkey"
        assert alerts[0]["age_days"] > 30

    def test_no_alert_for_fresh_keys(self):
        """No alert should be triggered for keys within age threshold."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            max_key_age_days=30,
        )
        fresh_timestamp = pendulum.now("UTC") - pendulum.duration(days=10)

        manager.register_key(
            config_id="config-1",
            key_id="v1:freshkey",
            created_at=fresh_timestamp,
        )

        alerts = manager.check_key_age_alerts()
        assert len(alerts) == 0

    def test_alert_includes_age_details(self):
        """Alert should include helpful age information."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            max_key_age_days=90,
        )
        config_id = "config-1"
        old_timestamp = pendulum.now("UTC") - pendulum.duration(days=100)

        manager.register_key(
            config_id=config_id,
            key_id="v1:oldkey",
            created_at=old_timestamp,
        )

        alerts = manager.check_key_age_alerts()
        assert alerts[0]["max_age_days"] == 90
        assert alerts[0]["age_days"] >= 99  # Allow for test execution time

    def test_multiple_old_keys_generate_multiple_alerts(self):
        """Each old key should generate its own alert."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            max_key_age_days=30,
        )
        old_timestamp = pendulum.now("UTC") - pendulum.duration(days=45)

        manager.register_key(
            config_id="config-1",
            key_id="v1:key1",
            created_at=old_timestamp,
        )
        manager.register_key(
            config_id="config-2",
            key_id="v1:key2",
            created_at=old_timestamp,
        )

        alerts = manager.check_key_age_alerts()
        assert len(alerts) == 2


class TestKeyRotationSchedule:
    """Tests for automated rotation scheduling."""

    def test_get_keys_needing_rotation(self):
        """Should identify keys that need rotation based on schedule."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            rotation_interval_days=30,
        )
        old_timestamp = pendulum.now("UTC") - pendulum.duration(days=35)
        fresh_timestamp = pendulum.now("UTC") - pendulum.duration(days=10)

        manager.register_key(
            config_id="config-old",
            key_id="v1:oldkey",
            created_at=old_timestamp,
        )
        manager.register_key(
            config_id="config-fresh",
            key_id="v1:freshkey",
            created_at=fresh_timestamp,
        )

        keys_needing_rotation = manager.get_keys_needing_rotation()
        assert len(keys_needing_rotation) == 1
        assert keys_needing_rotation[0]["config_id"] == "config-old"

    def test_rotation_schedule_respects_interval(self):
        """Keys should be flagged for rotation based on interval."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            rotation_interval_days=90,
        )
        timestamp_89_days = pendulum.now("UTC") - pendulum.duration(days=89)
        timestamp_91_days = pendulum.now("UTC") - pendulum.duration(days=91)

        manager.register_key(
            config_id="config-89",
            key_id="v1:key89",
            created_at=timestamp_89_days,
        )
        manager.register_key(
            config_id="config-91",
            key_id="v1:key91",
            created_at=timestamp_91_days,
        )

        keys_needing_rotation = manager.get_keys_needing_rotation()
        config_ids = [k["config_id"] for k in keys_needing_rotation]
        assert "config-91" in config_ids
        assert "config-89" not in config_ids

    def test_days_until_rotation_calculation(self):
        """Should correctly calculate days until rotation needed."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager(
            rotation_interval_days=30,
        )
        timestamp_20_days_ago = pendulum.now("UTC") - pendulum.duration(days=20)

        manager.register_key(
            config_id="config-1",
            key_id="v1:key",
            created_at=timestamp_20_days_ago,
        )

        days_until = manager.get_days_until_rotation("config-1")
        assert 9 <= days_until <= 11  # Allow for test execution time


class TestKeyRotationMetrics:
    """Tests for Prometheus metrics related to key rotation."""

    def test_key_age_metric_exposed(self):
        """Key age should be exposed as a Prometheus metric."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()
        timestamp = pendulum.now("UTC") - pendulum.duration(days=15)

        manager.register_key(
            config_id="config-1",
            key_id="v1:key",
            created_at=timestamp,
        )

        metrics = manager.get_key_age_metrics()
        assert "config-1" in metrics
        assert 14 <= metrics["config-1"] <= 16

    def test_rotation_count_metric(self):
        """Rotation count should be tracked as a metric."""
        from src.llm_config.key_rotation import KeyRotationManager

        manager = KeyRotationManager()

        manager.record_rotation_event(
            config_id="config-1",
            old_key_id="v1:a",
            new_key_id="v1:b",
            reason="scheduled",
        )
        manager.record_rotation_event(
            config_id="config-1",
            old_key_id="v1:b",
            new_key_id="v1:c",
            reason="manual",
        )

        metrics = manager.get_rotation_count_metrics()
        assert metrics["config-1"]["total"] == 2
        assert metrics["config-1"]["scheduled"] == 1
        assert metrics["config-1"]["manual"] == 1


class TestKeyRotationLogging:
    """Tests for structured logging of rotation events."""

    def test_rotation_logs_to_structured_logger(self):
        """Rotation events should be logged with structured data."""
        from src.llm_config.key_rotation import KeyRotationManager

        with patch("src.llm_config.key_rotation.logger") as mock_logger:
            manager = KeyRotationManager()
            manager.record_rotation_event(
                config_id="config-1",
                old_key_id="v1:old",
                new_key_id="v1:new",
                reason="scheduled",
            )

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert "Key rotation recorded" in str(call_args)
            extra = call_args.kwargs.get("extra", {})
            assert extra.get("config_id") == "config-1"

    def test_alert_logs_as_warning(self):
        """Key age alerts should be logged at warning level."""
        from src.llm_config.key_rotation import KeyRotationManager

        with patch("src.llm_config.key_rotation.logger") as mock_logger:
            manager = KeyRotationManager(max_key_age_days=30)
            old_timestamp = pendulum.now("UTC") - pendulum.duration(days=45)

            manager.register_key(
                config_id="config-1",
                key_id="v1:oldkey",
                created_at=old_timestamp,
            )

            manager.check_key_age_alerts()

            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "exceeds maximum age" in str(call_args)
            extra = call_args.kwargs.get("extra", {})
            assert extra.get("config_id") == "config-1"


class TestKeyRotationIntegrationWithEncryptionService:
    """Tests for integration between KeyRotationManager and EncryptionService."""

    def test_rotation_manager_can_trigger_key_rotation(self):
        """KeyRotationManager should be able to coordinate with EncryptionService."""
        import base64
        import secrets

        from src.llm_config.encryption import EncryptionService
        from src.llm_config.key_rotation import KeyRotationManager

        master_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        encryption_service = EncryptionService(master_key)
        manager = KeyRotationManager()

        original_data = "secret-api-key-12345"
        encrypted_data, old_key_id, _preview = encryption_service.encrypt_api_key(original_data)

        manager.register_key(
            config_id="config-1",
            key_id=old_key_id,
            created_at=pendulum.now("UTC") - pendulum.duration(days=100),
        )

        new_encrypted_data, new_key_id, _new_preview = encryption_service.rotate_key(
            encrypted_data, old_key_id
        )

        manager.record_rotation_event(
            config_id="config-1",
            old_key_id=old_key_id,
            new_key_id=new_key_id,
            reason="scheduled",
        )
        manager.update_key_registration(
            config_id="config-1",
            key_id=new_key_id,
            created_at=pendulum.now("UTC"),
        )

        decrypted = encryption_service.decrypt_api_key(new_encrypted_data, new_key_id)
        assert decrypted == original_data
        assert new_key_id != old_key_id

        events = manager.get_rotation_history("config-1")
        assert len(events) == 1
