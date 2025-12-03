"""
Key rotation automation for encrypted API keys.

Provides automated key rotation scheduling, audit trail logging,
and alerting when keys exceed configured age thresholds.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import TypedDict

from src.monitoring import get_logger

logger = get_logger(__name__)


class RotationEvent(TypedDict):
    """Structure for rotation event audit trail entries."""

    timestamp: str
    old_key_id: str
    new_key_id: str
    reason: str


class KeyAgeAlert(TypedDict):
    """Structure for key age alert data."""

    config_id: str
    key_id: str
    age_days: float
    max_age_days: int
    created_at: str


class KeyRotationNeeded(TypedDict):
    """Structure for keys needing rotation."""

    config_id: str
    key_id: str
    age_days: float
    rotation_interval_days: int
    created_at: str


class KeyRegistration(TypedDict):
    """Structure for registered key data."""

    key_id: str
    created_at: datetime


class RotationCountMetrics(TypedDict):
    """Structure for rotation count metrics."""

    total: int
    scheduled: int
    manual: int


class KeyRotationManager:
    """
    Manages encryption key rotation automation.

    Provides:
    - Audit trail for all rotation events
    - Key age tracking and alerting
    - Configurable rotation schedules
    - Prometheus-compatible metrics
    """

    def __init__(
        self,
        rotation_interval_days: int = 90,
        max_key_age_days: int = 180,
    ) -> None:
        """
        Initialize the key rotation manager.

        Args:
            rotation_interval_days: Days between automatic key rotations.
                Keys older than this will be flagged for rotation.
            max_key_age_days: Maximum allowed key age before alerting.
                Keys older than this trigger warnings.
        """
        self.rotation_interval_days = rotation_interval_days
        self.max_key_age_days = max_key_age_days

        self._audit_trail: dict[str, list[RotationEvent]] = defaultdict(list)
        self._key_registry: dict[str, KeyRegistration] = {}
        self._rotation_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "scheduled": 0, "manual": 0}
        )

    def record_rotation_event(
        self,
        config_id: str,
        old_key_id: str,
        new_key_id: str,
        reason: str,
    ) -> None:
        """
        Record a key rotation event in the audit trail.

        Args:
            config_id: Identifier for the LLM configuration
            old_key_id: The key ID being rotated out
            new_key_id: The new key ID being rotated in
            reason: Reason for rotation (e.g., "scheduled", "manual", "security")
        """
        event: RotationEvent = {
            "timestamp": datetime.now(UTC).isoformat(),
            "old_key_id": old_key_id,
            "new_key_id": new_key_id,
            "reason": reason,
        }
        self._audit_trail[config_id].append(event)

        self._rotation_counts[config_id]["total"] += 1
        if reason in ("scheduled", "manual"):
            self._rotation_counts[config_id][reason] += 1

        logger.info(
            "Key rotation recorded",
            extra={
                "config_id": config_id,
                "old_key_id": old_key_id[:20] + "..." if len(old_key_id) > 20 else old_key_id,
                "new_key_id": new_key_id[:20] + "..." if len(new_key_id) > 20 else new_key_id,
                "reason": reason,
            },
        )

    def get_rotation_history(self, config_id: str) -> list[RotationEvent]:
        """
        Get the rotation audit trail for a configuration.

        Args:
            config_id: Identifier for the LLM configuration

        Returns:
            List of rotation events in chronological order
        """
        return list(self._audit_trail[config_id])

    def register_key(
        self,
        config_id: str,
        key_id: str,
        created_at: datetime,
    ) -> None:
        """
        Register a key for age tracking.

        Args:
            config_id: Identifier for the LLM configuration
            key_id: The key ID to track
            created_at: When the key was created
        """
        self._key_registry[config_id] = {
            "key_id": key_id,
            "created_at": created_at,
        }

    def update_key_registration(
        self,
        config_id: str,
        key_id: str,
        created_at: datetime,
    ) -> None:
        """
        Update an existing key registration after rotation.

        Args:
            config_id: Identifier for the LLM configuration
            key_id: The new key ID
            created_at: When the new key was created
        """
        self.register_key(config_id, key_id, created_at)

    def check_key_age_alerts(self) -> list[KeyAgeAlert]:
        """
        Check for keys that exceed the maximum age threshold.

        Returns:
            List of alerts for keys exceeding max_key_age_days
        """
        alerts: list[KeyAgeAlert] = []
        now = datetime.now(UTC)

        for config_id, registration in self._key_registry.items():
            age = now - registration["created_at"]
            age_days = age.total_seconds() / 86400

            if age_days > self.max_key_age_days:
                alert: KeyAgeAlert = {
                    "config_id": config_id,
                    "key_id": registration["key_id"],
                    "age_days": age_days,
                    "max_age_days": self.max_key_age_days,
                    "created_at": registration["created_at"].isoformat(),
                }
                alerts.append(alert)

                logger.warning(
                    "Encryption key exceeds maximum age threshold",
                    extra={
                        "config_id": config_id,
                        "key_id": registration["key_id"][:20] + "..."
                        if len(registration["key_id"]) > 20
                        else registration["key_id"],
                        "age_days": round(age_days, 1),
                        "max_age_days": self.max_key_age_days,
                    },
                )

        return alerts

    def get_keys_needing_rotation(self) -> list[KeyRotationNeeded]:
        """
        Get keys that are due for scheduled rotation.

        Returns:
            List of keys that have exceeded rotation_interval_days
        """
        keys_needing_rotation: list[KeyRotationNeeded] = []
        now = datetime.now(UTC)

        for config_id, registration in self._key_registry.items():
            age = now - registration["created_at"]
            age_days = age.total_seconds() / 86400

            if age_days > self.rotation_interval_days:
                key_info: KeyRotationNeeded = {
                    "config_id": config_id,
                    "key_id": registration["key_id"],
                    "age_days": age_days,
                    "rotation_interval_days": self.rotation_interval_days,
                    "created_at": registration["created_at"].isoformat(),
                }
                keys_needing_rotation.append(key_info)

        return keys_needing_rotation

    def get_days_until_rotation(self, config_id: str) -> float:
        """
        Calculate days until a key needs rotation.

        Args:
            config_id: Identifier for the LLM configuration

        Returns:
            Days until rotation is needed (negative if overdue)

        Raises:
            KeyError: If config_id is not registered
        """
        if config_id not in self._key_registry:
            raise KeyError(f"Config {config_id} not registered for key rotation tracking")

        registration = self._key_registry[config_id]
        age = datetime.now(UTC) - registration["created_at"]
        age_days = age.total_seconds() / 86400

        return self.rotation_interval_days - age_days

    def get_key_age_metrics(self) -> dict[str, float]:
        """
        Get key age metrics for Prometheus export.

        Returns:
            Dictionary mapping config_id to age in days
        """
        metrics: dict[str, float] = {}
        now = datetime.now(UTC)

        for config_id, registration in self._key_registry.items():
            age = now - registration["created_at"]
            age_days = age.total_seconds() / 86400
            metrics[config_id] = age_days

        return metrics

    def get_rotation_count_metrics(self) -> dict[str, RotationCountMetrics]:
        """
        Get rotation count metrics for Prometheus export.

        Returns:
            Dictionary mapping config_id to rotation counts by reason
        """
        return {
            config_id: RotationCountMetrics(
                total=counts["total"],
                scheduled=counts["scheduled"],
                manual=counts["manual"],
            )
            for config_id, counts in self._rotation_counts.items()
        }
