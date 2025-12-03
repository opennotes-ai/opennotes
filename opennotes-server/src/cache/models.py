from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class CacheEntrySchema(BaseModel):
    """
    Pydantic model for cache entry serialization/API responses.

    This model is used for API endpoints and data serialization, not for
    internal cache storage. For internal cache storage, use the CacheEntry
    dataclass from src.cache.interfaces.
    """

    key: str = Field(..., description="Cache key")
    value: Any = Field(..., description="Cached value")
    ttl: int | None = Field(None, description="Time to live in seconds")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = Field(None, description="Expiration timestamp")


class SessionData(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    user_id: int = Field(..., description="User ID associated with this session")
    username: str = Field(..., description="Username")
    device_id: str | None = Field(None, description="Device identifier for multi-device support")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional session metadata. Kept as dict[str, Any] - allows flexible "
        "storage of platform-specific session data (OAuth tokens, permissions, etc.)",
    )

    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    def refresh(self, ttl: int) -> None:
        self.last_accessed = datetime.now(UTC)
        self.expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
