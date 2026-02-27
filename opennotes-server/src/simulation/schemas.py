import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema, TimestampSchema
from src.llm_config.model_id import ModelId

REASONING_MODEL_PATTERN = re.compile(r"^o[1-9]\d*(-mini|-preview|-pro)?(-\d{4}-\d{2}-\d{2})?$")


def validate_model_name_value(v: str) -> str:
    try:
        model_id = ModelId.from_pydantic_ai(v)
    except ValueError as exc:
        raise ValueError(
            f"Invalid model name '{v}'. Use 'provider:model' format "
            f"(e.g. 'openai:gpt-4o-mini', 'google-gla:gemini-2.0-flash')."
        ) from exc
    if REASONING_MODEL_PATTERN.match(model_id.model):
        raise ValueError(
            f"Reasoning model '{v}' is not supported for simulation agents. "
            f"Reasoning models (o1, o3, o4-mini, etc.) reject tool result messages "
            f"not preceded by tool_calls. Use a non-reasoning model like 'openai:gpt-4o-mini'."
        )
    return v


class ModelNameResponse(SQLAlchemySchema):
    provider: str
    model: str


class SimAgentBase(StrictInputSchema):
    name: str = Field(..., max_length=255)
    personality: str
    model_name: str = Field(..., max_length=100)
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str = Field(default="sliding_window", max_length=50)
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        return validate_model_name_value(v)


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

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_model_name_value(v)


class SimActionType(str, Enum):
    WRITE_NOTE = "write_note"
    RATE_NOTE = "rate_note"
    REACT_TO_NOTE = "react_to_note"
    PASS_TURN = "pass_turn"


PHASE1_ALLOWED_ACTIONS = {
    SimActionType.WRITE_NOTE,
    SimActionType.RATE_NOTE,
    SimActionType.PASS_TURN,
}


class ActionSelectionResult(BaseModel):
    action_type: SimActionType
    reasoning: str = Field(..., description="Why this action was chosen")

    @field_validator("action_type")
    @classmethod
    def validate_allowed_actions(cls, v: SimActionType) -> SimActionType:
        if v not in PHASE1_ALLOWED_ACTIONS:
            raise ValueError(
                f"Phase 1 only allows: {', '.join(a.value for a in PHASE1_ALLOWED_ACTIONS)}"
            )
        return v


class SimAgentAction(BaseModel):
    action_type: SimActionType
    request_id: str | None = Field(None, description="Request ID the note was written for")
    note_id: str | None = Field(None, description="Note ID that was rated or reacted to")
    summary: str | None = Field(None, description="Note summary text if wrote a note")
    classification: str | None = Field(None, description="Note classification if wrote a note")
    helpfulness_level: str | None = Field(None, description="Rating level if rated a note")
    reaction_text: str | None = Field(None, description="Reaction text if reacted")
    reasoning: str = Field(..., description="Brief explanation of why this action was chosen")


class SimAgentResponse(TimestampSchema):
    id: UUID
    name: str
    personality: str
    model_name: ModelNameResponse
    model_params: dict[str, Any] | None = None
    tool_config: dict[str, Any] | None = None
    memory_compaction_strategy: str
    memory_compaction_config: dict[str, Any] | None = None
    community_server_id: UUID | None = None
    deleted_at: datetime | None = None

    @field_validator("model_name", mode="before")
    @classmethod
    def parse_model_name(cls, v: Any) -> ModelNameResponse | dict[str, str]:
        if isinstance(v, ModelNameResponse):
            return v
        if isinstance(v, str):
            if ":" in v:
                mid = ModelId.from_pydantic_ai(v)
                return ModelNameResponse(provider=mid.provider, model=mid.model)
            return ModelNameResponse(provider="unknown", model=v)
        if isinstance(v, dict):
            return ModelNameResponse(**v)
        msg = f"Expected str or dict for model_name, got {type(v)}"
        raise ValueError(msg)


class PlaygroundNoteRequestAttributes(StrictInputSchema):
    urls: list[AnyHttpUrl] = Field(..., min_length=1, max_length=20)
    requested_by: str = Field(default="system-playground")


class PlaygroundNoteRequestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["playground-note-requests"]
    attributes: PlaygroundNoteRequestAttributes


class PlaygroundNoteRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: PlaygroundNoteRequestData


class PlaygroundNoteRequestResultAttributes(SQLAlchemySchema):
    request_id: str
    requested_by: str
    status: str
    community_server_id: str
    content: str | None = None
    url: str
    error: str | None = None


class PlaygroundNoteRequestResultResource(BaseModel):
    type: str = "requests"
    id: str
    attributes: PlaygroundNoteRequestResultAttributes


class PlaygroundNoteRequestListResponse(SQLAlchemySchema):
    data: list[PlaygroundNoteRequestResultResource]
    jsonapi: dict[str, str] = {"version": "1.1"}
    meta: dict[str, Any] | None = None


class PlaygroundNoteRequestJobAttributes(BaseModel):
    workflow_id: str
    url_count: int
    status: str = "ACCEPTED"


class PlaygroundNoteRequestJobResource(BaseModel):
    type: str = "playground-note-request-jobs"
    id: str
    attributes: PlaygroundNoteRequestJobAttributes


class PlaygroundNoteRequestJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data: PlaygroundNoteRequestJobResource
    jsonapi: dict[str, str] = {"version": "1.1"}
