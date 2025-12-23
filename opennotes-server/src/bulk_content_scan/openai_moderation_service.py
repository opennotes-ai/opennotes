"""OpenAI moderation service for content scanning."""

import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

MODERATION_MODEL = "omni-moderation-latest"


@dataclass
class ModerationResult:
    """Result from OpenAI moderation API."""

    flagged: bool
    categories: dict[str, bool]
    scores: dict[str, float]
    max_score: float
    flagged_categories: list[str] = field(default_factory=list)


class OpenAIModerationService:
    """Service for moderating content using OpenAI's moderation API."""

    def __init__(self, client: AsyncOpenAI):
        """Initialize the service with an OpenAI client.

        Args:
            client: AsyncOpenAI client instance
        """
        self.client = client

    async def moderate_text(self, text: str) -> ModerationResult:
        """Moderate text content.

        Args:
            text: The text content to moderate

        Returns:
            ModerationResult with flagged status and category scores
        """
        response = await self.client.moderations.create(
            model=MODERATION_MODEL,
            input=[{"type": "text", "text": text}],
        )

        return self._parse_response(response)

    async def moderate_image(self, image_url: str) -> ModerationResult:
        """Moderate an image by URL.

        Args:
            image_url: URL of the image to moderate

        Returns:
            ModerationResult with flagged status and category scores
        """
        response = await self.client.moderations.create(
            model=MODERATION_MODEL,
            input=[{"type": "image_url", "image_url": {"url": image_url}}],
        )

        return self._parse_response(response)

    async def moderate_multimodal(self, text: str, image_urls: list[str]) -> ModerationResult:
        """Moderate text and images together.

        Args:
            text: The text content to moderate
            image_urls: List of image URLs to moderate

        Returns:
            ModerationResult with flagged status and category scores
        """
        input_items: list[Any] = [{"type": "text", "text": text}]
        for url in image_urls:
            input_items.append({"type": "image_url", "image_url": {"url": url}})

        response = await self.client.moderations.create(
            model=MODERATION_MODEL,
            input=input_items,  # type: ignore[arg-type]
        )

        return self._parse_response(response)

    def _parse_response(self, response) -> ModerationResult:
        """Parse the OpenAI moderation response into ModerationResult.

        Args:
            response: Response from OpenAI moderations.create()

        Returns:
            ModerationResult with parsed categories and scores
        """
        result = response.results[0]

        categories = {}
        scores = {}

        categories_obj = result.categories
        scores_obj = result.category_scores

        category_names = [
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

        for name in category_names:
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
