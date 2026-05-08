from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

FeedbackType = Literal["thumbs_up", "thumbs_down", "message"]

_MESSAGE_MAX_LENGTH = 4000


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
    message: str | None = Field(default=None, max_length=_MESSAGE_MAX_LENGTH)
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
    message: str | None = Field(default=None, max_length=_MESSAGE_MAX_LENGTH)
    final_type: FeedbackType


FeedbackRequest = Annotated[
    Union[FeedbackOpenRequest, FeedbackCombinedRequest],
    Field(discriminator="kind"),
]
