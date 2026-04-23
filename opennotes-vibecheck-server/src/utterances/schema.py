from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.analyses.schemas import PageKind


class Utterance(BaseModel):
    utterance_id: str | None = None
    kind: Literal["post", "comment", "reply"]
    text: str
    author: str | None = None
    timestamp: datetime | None = None
    parent_id: str | None = None
    mentioned_urls: list[str] = Field(default_factory=list)
    mentioned_images: list[str] = Field(default_factory=list)
    mentioned_videos: list[str] = Field(default_factory=list)


class UtterancesPayload(BaseModel):
    source_url: str
    scraped_at: datetime
    utterances: list[Utterance]
    page_title: str | None = None
    page_kind: PageKind = PageKind.OTHER
