"""OpenAI moderation service for vibecheck-server.

Minimal port of opennotes-server's OpenAIModerationService scoped to the
text-only path needed for POC. Firecrawl utterances are always text, so the
multimodal helpers from the server are intentionally omitted.

This is the ONE module in vibecheck-server that talks to OpenAI. Every other
analysis uses pydantic-ai via Vertex Gemini.
"""

from __future__ import annotations

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

MODERATION_MODEL = "omni-moderation-latest"

MODERATION_CATEGORY_NAMES = [
    "violence",
    "violence/graphic",
    "sexual",
    "sexual/minors",
    "hate",
    "hate/threatening",
    "harassment",
    "harassment/threatening",
    "self-harm",
    "self-harm/intent",
    "self-harm/instructions",
    "illicit",
    "illicit/violent",
]


class ModerationResult(BaseModel):
    """Normalized result from the OpenAI moderation API."""

    flagged: bool
    categories: dict[str, bool]
    scores: dict[str, float]
    max_score: float
    flagged_categories: list[str] = Field(default_factory=list)


class OpenAIModerationService:
    """Service for moderating text content using OpenAI's moderation API."""

    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def moderate_text(self, text: str) -> ModerationResult:
        """Moderate a single piece of text.

        Args:
            text: The text content to moderate.

        Returns:
            ModerationResult with flagged status and category scores.
        """
        response = await self.client.moderations.create(
            model=MODERATION_MODEL,
            input=[{"type": "text", "text": text}],
        )
        return self._parse_response(response.results[0])

    async def moderate_texts(self, texts: list[str]) -> list[ModerationResult]:
        """Moderate multiple texts in ONE request.

        OpenAI's moderation endpoint accepts an array input and returns one
        result per input in order. Empty input -> empty output (no call).
        """
        if not texts:
            return []
        response = await self.client.moderations.create(
            model=MODERATION_MODEL,
            input=[{"type": "text", "text": t} for t in texts],
        )
        return [self._parse_response(r) for r in response.results]

    def _parse_response(self, result) -> ModerationResult:
        categories: dict[str, bool] = {}
        scores: dict[str, float] = {}
        categories_obj = result.categories
        scores_obj = result.category_scores
        for name in MODERATION_CATEGORY_NAMES:
            attr_name = name.replace("/", "_").replace("-", "_")
            if hasattr(categories_obj, attr_name):
                categories[name] = getattr(categories_obj, attr_name)
            if hasattr(scores_obj, attr_name):
                scores[name] = getattr(scores_obj, attr_name)

        flagged_categories = [name for name, flagged in categories.items() if flagged]
        max_score = max(scores.values()) if scores else 0.0

        return ModerationResult(
            flagged=result.flagged,
            categories=categories,
            scores=scores,
            max_score=max_score,
            flagged_categories=flagged_categories,
        )
