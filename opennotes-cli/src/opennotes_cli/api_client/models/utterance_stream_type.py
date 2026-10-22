from enum import Enum


class UtteranceStreamType(str, Enum):
    ARTICLE_OR_MONOLOGUE = "article_or_monologue"
    COMMENT_SECTION = "comment_section"
    DIALOGUE = "dialogue"
    MIXED = "mixed"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
