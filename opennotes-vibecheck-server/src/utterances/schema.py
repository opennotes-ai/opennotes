from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Utterance(BaseModel):
    utterance_id: str | None = None
    kind: Literal["post", "comment", "reply"]
    text: str
    author: str | None = None
    timestamp: datetime | None = None
    parent_id: str | None = None


class UtterancesPayload(BaseModel):
    source_url: str
    scraped_at: datetime
    utterances: list[Utterance]
    page_title: str | None = None
    page_kind: Literal["blog_post", "forum_thread", "article", "other"] = "other"
