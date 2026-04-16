"""ContentReviewerAgent for structured content moderation classification.

Module-level pydantic-ai Agent that classifies content using pre-computed evidence
(similarity hits, OpenAI moderation results) injected as dynamic instructions.
Supports flashpoint detection as an optional tool registered on the agent.

Follows the ClaimRelevanceService pattern from src/claim_relevance_check/service.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import UsageLimits

from src.bulk_content_scan.capabilities.flashpoint import detect_flashpoint
from src.bulk_content_scan.schemas import (
    ContentItem,
    ContentModerationClassificationResult,
    ConversationFlashpointMatch,
    OpenAIModerationMatch,
    SimilarityMatch,
)
from src.config import settings as default_settings

if TYPE_CHECKING:
    from src.bulk_content_scan.flashpoint_service import FlashpointDetectionService
from src.monitoring import get_logger

logger = get_logger(__name__)

_DEFAULT_CONTENT_REVIEWER_TIMEOUT = 30.0

_DEFAULT_MAX_TOKENS = 1024

_DEFAULT_REQUEST_LIMIT = 5

_DEFAULT_TOTAL_TOKENS_LIMIT = 8192

_STATIC_INSTRUCTIONS = """\
You are a content moderation classifier. Analyze the content and any pre-computed \
evidence to produce a structured classification decision.

Produce a ContentModerationClassificationResult with:
- confidence: float 0.0-1.0 reflecting your certainty
- category_labels: dict mapping category names to true/false
- category_scores: optional per-category confidence scores (keys must be a subset of category_labels keys)
- recommended_action: one of 'pass', 'review', 'hide' (or null)
- action_tier: one of 'tier_1_immediate', 'tier_2_consensus' (or null; only set when recommended_action is also set)
- explanation: brief human-readable reasoning\
"""


@dataclass
class ContentReviewerDeps:
    """Dependencies injected into the ContentReviewerAgent at runtime.

    flashpoint_service: FlashpointDetectionService instance, or None if not configured.
    context_items: Previous content items in the channel (time-ordered), used for
        flashpoint detection context.
    """

    flashpoint_service: FlashpointDetectionService | None
    context_items: list[ContentItem] = field(default_factory=list)


content_reviewer_agent: Agent[ContentReviewerDeps, ContentModerationClassificationResult] = Agent(
    name="content-reviewer",
    output_type=ContentModerationClassificationResult,
    deps_type=ContentReviewerDeps,
    instrument=True,
    retries=2,
    instructions=_STATIC_INSTRUCTIONS,
)


@content_reviewer_agent.output_validator
def _validate_output(
    output: ContentModerationClassificationResult,
) -> ContentModerationClassificationResult:
    """Enforce cross-field invariants on the classification result.

    Raises ModelRetry if:
    - action_tier is set without recommended_action
    - category_scores keys are not a subset of category_labels keys
    """
    if output.action_tier is not None and output.recommended_action is None:
        raise ModelRetry(
            "action_tier must not be set when recommended_action is null. "
            "Either set recommended_action or clear action_tier."
        )

    if output.category_scores is not None:
        label_keys = set(output.category_labels.keys())
        score_keys = set(output.category_scores.keys())
        extra_keys = score_keys - label_keys
        if extra_keys:
            raise ModelRetry(
                f"category_scores keys {extra_keys!r} are not present in category_labels. "
                "category_scores keys must be a subset of category_labels keys."
            )

    return output


@content_reviewer_agent.tool
async def detect_flashpoint_tool(
    ctx: RunContext[ContentReviewerDeps],
    content_item: ContentItem,
) -> str:
    """Detect conversation flashpoint patterns for the given content item.

    Use this tool when the content shows signs of escalating conflict or hostility
    and you want to assess derailment risk in the conversation thread.

    Args:
        content_item: The content item to analyze for flashpoint patterns.

    Returns:
        A string describing the flashpoint detection result.
    """
    result = await detect_flashpoint(
        content_item=content_item,
        context_items=ctx.deps.context_items,
        flashpoint_service=ctx.deps.flashpoint_service,
    )
    if result is None:
        return "No flashpoint detected"
    return (
        f"Flashpoint detected: risk_level={result.risk_level}, "
        f"score={result.derailment_score}, reasoning={result.reasoning}"
    )


def _fail_open(reason: str) -> ContentModerationClassificationResult:
    """Return a fail-open classification result on timeout or error.

    Confidence=0.0 signals that the classification could not be completed and
    downstream code should treat this as unreviewed content.
    """
    return ContentModerationClassificationResult(
        confidence=0.0,
        category_labels={},
        category_scores=None,
        recommended_action=None,
        action_tier=None,
        explanation=f"Classification failed: {reason}",
    )


class ContentReviewerService:
    """Classifies content using the ContentReviewerAgent with pre-computed evidence.

    Pre-computed evidence (similarity hits, OpenAI moderation results) is formatted
    and injected as the user prompt so the agent can reason over it alongside
    the raw content. The static system instructions are set once at module level
    via Agent(instructions=_STATIC_INSTRUCTIONS) to enable Anthropic prompt caching.

    Implements fail-open semantics: on timeout or unexpected error, returns a
    classification with confidence=0.0 so downstream logic can decide how to handle
    unreviewed content.

    The settings parameter allows callers to inject their own module-scoped settings
    reference, enabling test patches to work transparently. When not provided, the
    global settings singleton is used.
    """

    def __init__(self, settings: Any = None) -> None:
        self._settings = settings if settings is not None else default_settings

    def _build_instructions(
        self,
        content_item: ContentItem,
        pre_computed_evidence: Sequence[
            SimilarityMatch | OpenAIModerationMatch | ConversationFlashpointMatch
        ],
    ) -> str:
        """Build dynamic user prompt content from the content item and pre-computed evidence.

        Returns only the dynamic portion (ContentItem + evidence). The static preamble
        and output schema description live in _STATIC_INSTRUCTIONS and are set on the
        Agent directly.
        """
        lines: list[str] = [
            f"Content to classify (platform={content_item.platform}, id={content_item.content_id}):",
            content_item.content_text,
            "",
        ]

        if pre_computed_evidence:
            lines.append("Pre-computed evidence:")
            for evidence in pre_computed_evidence:
                if isinstance(evidence, SimilarityMatch):
                    lines.append(
                        f"- Fact-check match: '{evidence.matched_claim}' "
                        f"(score: {evidence.score:.2f}, source: {evidence.matched_source})"
                    )
                elif isinstance(evidence, OpenAIModerationMatch):
                    flagged = (
                        ", ".join(evidence.flagged_categories)
                        if evidence.flagged_categories
                        else "none"
                    )
                    lines.append(
                        f"- OpenAI moderation flagged: {flagged} "
                        f"(max_score: {evidence.max_score:.2f})"
                    )
                elif isinstance(evidence, ConversationFlashpointMatch):
                    lines.append(
                        f"- Conversation flashpoint detected: risk_level={evidence.risk_level}, "
                        f"derailment_score={evidence.derailment_score}/100, "
                        f"reasoning: {evidence.reasoning}"
                    )
            lines.append("")

        return "\n".join(lines)

    async def classify(
        self,
        content_item: ContentItem,
        pre_computed_evidence: Sequence[
            SimilarityMatch | OpenAIModerationMatch | ConversationFlashpointMatch
        ],
        context_items: list[ContentItem] | None = None,
        flashpoint_service: FlashpointDetectionService | None = None,
        model: Any = None,
    ) -> ContentModerationClassificationResult:
        """Classify content using the agent with pre-computed evidence.

        Builds a dynamic user prompt from the content item and evidence, runs the
        agent, and returns the structured classification result.

        Args:
            content_item: The content item to classify.
            pre_computed_evidence: List of SimilarityMatch and/or OpenAIModerationMatch
                results already computed by upstream scan steps.
            context_items: Previous content items in the channel (for flashpoint context).
            flashpoint_service: Optional FlashpointDetectionService instance.
            model: Optional model override (useful for testing with TestModel).

        Returns:
            ContentModerationClassificationResult. On timeout or unexpected error,
            returns a fail-open result with confidence=0.0.
        """
        cfg = self._settings
        timeout = getattr(cfg, "CONTENT_REVIEWER_TIMEOUT", _DEFAULT_CONTENT_REVIEWER_TIMEOUT)
        model_override = model or getattr(cfg, "CONTENT_REVIEWER_MODEL", None)
        max_tokens = getattr(cfg, "CONTENT_REVIEWER_MAX_TOKENS", _DEFAULT_MAX_TOKENS)
        request_limit = getattr(cfg, "CONTENT_REVIEWER_REQUEST_LIMIT", _DEFAULT_REQUEST_LIMIT)
        total_tokens_limit = getattr(
            cfg, "CONTENT_REVIEWER_TOTAL_TOKENS_LIMIT", _DEFAULT_TOTAL_TOKENS_LIMIT
        )

        user_prompt = self._build_instructions(
            content_item=content_item,
            pre_computed_evidence=pre_computed_evidence,
        )
        deps = ContentReviewerDeps(
            flashpoint_service=flashpoint_service,
            context_items=context_items or [],
        )

        try:
            run_kwargs: dict[str, Any] = {
                "deps": deps,
                "model_settings": ModelSettings(
                    temperature=0.0,
                    max_tokens=max_tokens,
                ),
                "usage_limits": UsageLimits(
                    request_limit=request_limit,
                    total_tokens_limit=total_tokens_limit,
                ),
            }
            if model_override is not None:
                run_kwargs["model"] = model_override

            agent_result = await asyncio.wait_for(
                content_reviewer_agent.run(
                    user_prompt,
                    **run_kwargs,
                ),
                timeout=timeout,
            )
            return agent_result.output

        except TimeoutError:
            logger.warning(
                "ContentReviewerAgent timed out",
                extra={
                    "content_id": content_item.content_id,
                    "timeout_seconds": timeout,
                },
            )
            return _fail_open(f"timeout after {timeout}s")

        except UnexpectedModelBehavior as e:
            logger.warning(
                "ContentReviewerAgent output parse failure",
                extra={
                    "content_id": content_item.content_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return _fail_open(str(e))

        except (ModelHTTPError, ModelAPIError) as e:
            logger.warning(
                "ContentReviewerAgent transport error",
                extra={
                    "content_id": content_item.content_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return _fail_open(str(e))

        except Exception as e:
            logger.warning(
                "ContentReviewerAgent failed",
                extra={
                    "content_id": content_item.content_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            return _fail_open(str(e))
