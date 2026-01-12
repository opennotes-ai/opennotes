"""
Database models for community server LLM configuration.

Provides tables for:
- Community servers (Discord guilds, subreddits, Slack workspaces, etc.)
- LLM provider configurations with encrypted API keys
- Usage tracking for rate limiting and budget management
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.community_config.models import CommunityConfig


class CommunityServer(Base):
    """
    Represents a single community server instance.

    Platform-agnostic model for tracking communities across different platforms
    (Discord servers/guilds, subreddits, Slack workspaces, Matrix spaces, etc.).

    Attributes:
        id: Unique community server identifier (UUID)
        platform: Platform type ('discord', 'reddit', 'slack', 'matrix', etc.)
        platform_community_server_id: Platform-specific identifier (e.g., Discord guild ID, subreddit name)
        name: Human-readable community server name
        description: Optional community description
        settings: JSON blob for community-specific settings
        is_active: Whether the community server is currently active
        is_public: Whether the community server is publicly visible (affects profile privacy)
        created_at: Timestamp when the community server was created
        updated_at: Timestamp of last update
        llm_configs: Related LLM configurations for this community server
    """

    __tablename__ = "community_servers"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    platform_community_server_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    welcome_message_id: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Discord message ID of the welcome message in bot channel",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    llm_configs: Mapped[list["CommunityServerLLMConfig"]] = relationship(
        back_populates="community_server", lazy="selectin", cascade="all, delete-orphan"
    )
    configs: Mapped[list["CommunityConfig"]] = relationship(
        back_populates="community_server", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "idx_community_servers_platform_community_server_id",
            "platform",
            "platform_community_server_id",
            unique=True,
        ),
        Index("idx_community_servers_is_active", "is_active"),
        Index("idx_community_servers_is_public", "is_public"),
        CheckConstraint(
            "platform IN ('discord', 'reddit', 'slack', 'matrix', 'discourse', 'other')",
            name="ck_community_servers_platform",
        ),
    )

    def __repr__(self) -> str:
        return f"<CommunityServer(id={self.id}, platform='{self.platform}', name='{self.name}')>"


class CommunityServerLLMConfig(Base):
    """
    LLM provider configuration for a community server.

    Stores encrypted API keys and configuration for LLM providers (OpenAI, Anthropic, etc.)
    with support for rate limiting and budget tracking.

    Attributes:
        id: Unique configuration identifier (UUID)
        community_server_id: Foreign key to community_servers table
        provider: LLM provider name ('openai', 'anthropic', 'google', 'cohere', 'custom')
        api_key_encrypted: Encrypted API key (binary data)
        encryption_key_id: Key version identifier for key rotation support
        api_key_preview: Preview of API key showing last 4 characters (e.g., '...ABCD')
        enabled: Whether this provider configuration is currently enabled
        settings: JSON blob for provider-specific settings (models, temperature, etc.)
        daily_request_limit: Maximum daily API requests (None = unlimited)
        monthly_request_limit: Maximum monthly API requests (None = unlimited)
        daily_token_limit: Maximum daily tokens (None = unlimited)
        monthly_token_limit: Maximum monthly tokens (None = unlimited)
        current_daily_requests: Current daily request count
        current_monthly_requests: Current monthly request count
        current_daily_tokens: Current daily token usage
        current_monthly_tokens: Current monthly token usage
        last_daily_reset: Timestamp of last daily counter reset
        last_monthly_reset: Timestamp of last monthly counter reset
        version: Optimistic locking version number (incremented on each update)
        created_at: Timestamp when configuration was created
        updated_at: Timestamp of last update
        created_by: UUID of user who created this configuration
        community_server: Related CommunityServer instance
    """

    __tablename__ = "community_server_llm_config"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    api_key_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_preview: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False, index=True
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")

    daily_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_request_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    monthly_token_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_spend_limit: Mapped[float | None] = mapped_column(
        Numeric(10, 4), nullable=True, comment="Daily spending limit in USD"
    )
    monthly_spend_limit: Mapped[float | None] = mapped_column(
        Numeric(10, 4), nullable=True, comment="Monthly spending limit in USD"
    )

    current_daily_requests: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    current_monthly_requests: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    current_daily_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    current_monthly_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    current_daily_spend: Mapped[float] = mapped_column(
        Numeric(10, 4),
        default=0.0,
        server_default="0.0000",
        nullable=False,
        comment="Current daily spend in USD",
    )
    current_monthly_spend: Mapped[float] = mapped_column(
        Numeric(10, 4),
        default=0.0,
        server_default="0.0000",
        nullable=False,
        comment="Current monthly spend in USD",
    )

    last_daily_reset: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_monthly_reset: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    version: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    community_server: Mapped["CommunityServer"] = relationship(
        back_populates="llm_configs", lazy="selectin"
    )

    __table_args__ = (
        Index(
            "idx_llm_config_community_provider",
            "community_server_id",
            "provider",
            unique=True,
        ),
        Index("idx_llm_config_enabled", "community_server_id", "enabled"),
        CheckConstraint(
            "provider IN ('openai', 'anthropic', 'google', 'cohere', 'custom')",
            name="ck_llm_config_provider",
        ),
        CheckConstraint(
            "daily_request_limit IS NULL OR daily_request_limit > 0",
            name="ck_llm_config_daily_request_limit",
        ),
        CheckConstraint(
            "monthly_request_limit IS NULL OR monthly_request_limit > 0",
            name="ck_llm_config_monthly_request_limit",
        ),
        CheckConstraint(
            "daily_token_limit IS NULL OR daily_token_limit > 0",
            name="ck_llm_config_daily_token_limit",
        ),
        CheckConstraint(
            "monthly_token_limit IS NULL OR monthly_token_limit > 0",
            name="ck_llm_config_monthly_token_limit",
        ),
        CheckConstraint(
            "daily_spend_limit IS NULL OR daily_spend_limit > 0",
            name="ck_llm_config_daily_spend_limit",
        ),
        CheckConstraint(
            "monthly_spend_limit IS NULL OR monthly_spend_limit > 0",
            name="ck_llm_config_monthly_spend_limit",
        ),
    )

    def __repr__(self) -> str:
        return f"<CommunityServerLLMConfig(id={self.id}, provider='{self.provider}', enabled={self.enabled})>"


class LLMUsageLog(Base):
    """
    Audit log for LLM API usage.

    Tracks individual LLM API calls for monitoring, debugging, and compliance.

    Attributes:
        id: Unique log entry identifier (UUID)
        community_server_id: Foreign key to community_servers table
        provider: LLM provider used for this request
        model: Specific model used (e.g., 'gpt-4', 'claude-3-opus')
        tokens_used: Number of tokens consumed by this request
        success: Whether the API call succeeded
        error_message: Error message if the call failed
        timestamp: When this API call occurred
    """

    __tablename__ = "llm_usage_log"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4, index=True
    )
    community_server_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("community_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(
        Numeric(10, 6),
        default=0.0,
        server_default="0.000000",
        nullable=False,
        comment="Cost of this API call in USD",
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("idx_llm_usage_community_timestamp", "community_server_id", "timestamp"),
        Index("idx_llm_usage_provider_timestamp", "provider", "timestamp"),
        Index("idx_llm_usage_success", "success"),
    )

    def __repr__(self) -> str:
        return f"<LLMUsageLog(id={self.id}, provider='{self.provider}', model='{self.model}', success={self.success})>"


from src.community_config.models import CommunityConfig  # noqa: E402
