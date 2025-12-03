"""Pydantic schemas for LLM configuration API."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema


class LLMConfigCreate(StrictInputSchema):
    """Schema for creating a new LLM configuration."""

    provider: Literal["openai", "anthropic", "google", "cohere", "custom"]
    api_key: str = Field(..., min_length=1, description="API key for the LLM provider")
    enabled: bool = Field(default=True, description="Whether this configuration is enabled")
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific settings (model, temperature, etc.). Kept as dict[str, Any] - "
        "each LLM provider has different configuration options and parameters.",
    )
    daily_request_limit: int | None = Field(
        default=None, gt=0, description="Maximum daily API requests (None = unlimited)"
    )
    monthly_request_limit: int | None = Field(
        default=None, gt=0, description="Maximum monthly API requests (None = unlimited)"
    )
    daily_token_limit: int | None = Field(
        default=None, gt=0, description="Maximum daily tokens (None = unlimited)"
    )
    monthly_token_limit: int | None = Field(
        default=None, gt=0, description="Maximum monthly tokens (None = unlimited)"
    )
    daily_spend_limit: float | None = Field(
        default=None, gt=0, description="Maximum daily spending in USD (None = unlimited)"
    )
    monthly_spend_limit: float | None = Field(
        default=None, gt=0, description="Maximum monthly spending in USD (None = unlimited)"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_format(cls, v: str, info: Any) -> str:
        """Validate API key format based on provider."""
        provider = info.data.get("provider")
        if provider == "openai" and not v.startswith("sk-"):
            raise ValueError("OpenAI API keys must start with 'sk-'")
        if provider == "anthropic" and not v.startswith("sk-ant-"):
            raise ValueError("Anthropic API keys must start with 'sk-ant-'")
        return v


class LLMConfigUpdate(StrictInputSchema):
    """Schema for updating an existing LLM configuration."""

    api_key: str | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    settings: dict[str, Any] | None = None
    daily_request_limit: int | None = Field(default=None, gt=0)
    monthly_request_limit: int | None = Field(default=None, gt=0)
    daily_token_limit: int | None = Field(default=None, gt=0)
    monthly_token_limit: int | None = Field(default=None, gt=0)
    daily_spend_limit: float | None = Field(default=None, gt=0)
    monthly_spend_limit: float | None = Field(default=None, gt=0)


class LLMConfigResponse(SQLAlchemySchema):
    """Schema for LLM configuration response (excludes full API key)."""

    id: UUID
    community_server_id: UUID
    provider: str
    api_key_preview: str = Field(..., description="Last 4 characters of API key")
    enabled: bool
    settings: dict[str, Any]
    daily_request_limit: int | None
    monthly_request_limit: int | None
    daily_token_limit: int | None
    monthly_token_limit: int | None
    daily_spend_limit: float | None
    monthly_spend_limit: float | None
    current_daily_requests: int
    current_monthly_requests: int
    current_daily_tokens: int
    current_monthly_tokens: int
    current_daily_spend: float
    current_monthly_spend: float
    last_daily_reset: datetime | None
    last_monthly_reset: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None


class LLMConfigTestRequest(StrictInputSchema):
    """Schema for testing an LLM configuration."""

    provider: Literal["openai", "anthropic", "google", "cohere", "custom"]
    api_key: str = Field(..., min_length=1)
    settings: dict[str, Any] = Field(default_factory=dict)


class LLMConfigTestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    """Schema for LLM configuration test result."""

    valid: bool
    error_message: str | None = None


class LLMUsageStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    """Schema for usage statistics response."""

    provider: str
    daily_requests: dict[str, Any]
    monthly_requests: dict[str, Any]
    daily_tokens: dict[str, Any]
    monthly_tokens: dict[str, Any]
    daily_spend: dict[str, Any]
    monthly_spend: dict[str, Any]
    last_daily_reset: datetime | None
    last_monthly_reset: datetime | None
