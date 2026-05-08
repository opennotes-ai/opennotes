from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

FeedbackType = Literal["thumbs_up", "thumbs_down", "message"]


class FeedbackOpenRequest(BaseModel):
    page_path: str
    user_agent: str
    referrer: str = ""
    bell_location: str
    initial_type: FeedbackType


class FeedbackOpenResponse(BaseModel):
    id: UUID


class FeedbackSubmitRequest(BaseModel):
    email: EmailStr | None = None
    message: str | None = None
    final_type: FeedbackType


class FeedbackCombinedRequest(FeedbackOpenRequest):
    email: EmailStr | None = None
    message: str | None = None
    final_type: FeedbackType
