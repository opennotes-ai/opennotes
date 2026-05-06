from __future__ import annotations

from enum import StrEnum


class UtteranceStreamType(StrEnum):
    """Discourse shape observed in the extracted utterance stream."""

    DIALOGUE = "dialogue"
    COMMENT_SECTION = "comment_section"
    ARTICLE_OR_MONOLOGUE = "article_or_monologue"
    MIXED = "mixed"
    UNKNOWN = "unknown"
