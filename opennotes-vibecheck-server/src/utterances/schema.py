from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.analyses.schemas import PageKind, UtteranceStreamType


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
    utterance_stream_type: UtteranceStreamType = UtteranceStreamType.UNKNOWN


class SectionHint(BaseModel):
    anchor_hint: str
    tolerance_bytes: int | None = None
    parent_context_text: str | None = None
    overlap_with_prev_bytes: int | None = None


class BatchedUtteranceRedirectionResponse(BaseModel):
    page_kind: PageKind
    utterance_stream_type: UtteranceStreamType
    page_title: str | None = None
    boundary_instructions: str
    section_hints: list[SectionHint] = Field(default_factory=list)
