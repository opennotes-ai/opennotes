from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Discriminator, EmailStr, Field, Tag

FeedbackType = Literal["thumbs_up", "thumbs_down", "message"]


def _infer_feedback_kind(v: Any) -> str:
    """Infer the discriminator value from request body shape.

    Inference rule (backwards-compatible — kind field is optional):
    - body has 'final_type' key → treat as 'combined'
    - otherwise → treat as 'open'

    When 'kind' is present it takes precedence (Pydantic passes the raw
    dict before model instantiation so both dict and model instances are
    handled here).
    """
    if isinstance(v, dict):
        if "kind" in v:
            return str(v["kind"])
        return "combined" if "final_type" in v else "open"
    kind = getattr(v, "kind", None)
    if kind is not None:
        return str(kind)
    return "combined" if getattr(v, "final_type", None) is not None else "open"


class FeedbackOpenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["open"] = "open"
    page_path: str
    user_agent: str
    referrer: str = ""
    bell_location: str
    initial_type: FeedbackType


class FeedbackOpenResponse(BaseModel):
    id: UUID


class FeedbackSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    message: str | None = Field(default=None, max_length=4000)
    final_type: FeedbackType


class FeedbackCombinedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["combined"] = "combined"
    page_path: str
    user_agent: str
    referrer: str = ""
    bell_location: str
    initial_type: FeedbackType
    email: EmailStr | None = None
    message: str | None = Field(default=None, max_length=4000)
    final_type: FeedbackType


FeedbackRequest = Annotated[
    Annotated[FeedbackOpenRequest, Tag("open")]
    | Annotated[FeedbackCombinedRequest, Tag("combined")],
    Discriminator(_infer_feedback_kind),
]
