import hashlib
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.common.base_schemas import SQLAlchemySchema


def derive_tweet_id_from_platform_message_id(platform_message_id: str | None) -> str:
    """
    Derive a tweet_id string from platform_message_id for scoring system.

    This function converts a platform message ID (e.g., Discord message ID) into a
    string ID suitable for use with the external scoring system.

    Algorithm:
    - Hash the platform_message_id string using SHA256 for deterministic output
    - Extract first 16 hex characters and convert to integer
    - Ensure the result fits within BigInteger range (64-bit signed)
    - Convert to string for platform compatibility
    - Use deterministic hashing so the same platform_message_id always produces the same tweet_id

    Args:
        platform_message_id: Platform-specific message ID string

    Returns:
        String tweet_id for platform compatibility

    Raises:
        ValueError: If platform_message_id is None
    """
    if not platform_message_id:
        raise ValueError("platform_message_id cannot be None or empty")

    hash_value = int(hashlib.sha256(platform_message_id.encode()).hexdigest()[:16], 16)

    return str(hash_value & 0x7FFFFFFFFFFFFFFF)


class ScoringExportRequestBase(BaseModel):
    request_id: str = Field(..., description="Unique request identifier")
    tweet_id: str = Field(
        ..., min_length=1, description="Derived tweet_id for external scoring system"
    )
    requested_by: str = Field(..., description="Requester's participant ID")


class ScoringExportRequest(ScoringExportRequestBase, SQLAlchemySchema):
    """
    Schema for exporting requests to the external scoring algorithm.

    This schema includes the tweet_id field which is derived from platform_message_id.
    It's used when sending requests to external scoring systems that expect tweet-like IDs.

    Fields:
        - request_id: Unique identifier for the request
        - tweet_id: Derived BigInteger ID for scoring system (derived from platform_message_id)
        - requested_by: User who requested the note
    """

    id: UUID = Field(..., description="Unique request identifier in the system")
    community_server_id: UUID | None = Field(..., description="Community server ID")
    status: str = Field(..., description="Current request status")
    created_at: datetime = Field(..., description="Request creation timestamp")
