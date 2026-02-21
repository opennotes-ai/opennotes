from typing import Any
from uuid import UUID

from pydantic import Field

from src.common.base_schemas import StrictInputSchema, TimestampSchema


class SimAgentBase(StrictInputSchema):
    name: str = Field(..., max_length=255)
    personality: str
    model_name: str = Field(..., max_length=100)
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str = Field(default="sliding_window", max_length=50)
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None


class SimAgentCreate(SimAgentBase):
    pass


class SimAgentUpdate(StrictInputSchema):
    name: str | None = Field(default=None, max_length=255)
    personality: str | None = None
    model_name: str | None = Field(default=None, max_length=100)
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str | None = Field(default=None, max_length=50)
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None


class SimAgentResponse(TimestampSchema):
    id: UUID
    name: str
    personality: str
    model_name: str
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None
    deleted_at: str | None = None
