"""Shared service for LLM-based claim relevance checking.

Extracted from BulkContentScanService._check_relevance_with_llm() to enable
reuse across bulk scan and real-time monitor paths.
"""

import asyncio
import time
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.claim_relevance_check.prompt_optimization.prompts import get_optimized_prompts
from src.claim_relevance_check.schemas import (
    RelevanceCheckResult,
    RelevanceOutcome,
)
from src.config import settings as default_settings
from src.llm_config.providers.base import LLMMessage
from src.llm_config.service import LLMService
from src.monitoring import get_logger
from src.monitoring.metrics import relevance_check_total

logger = get_logger(__name__)


class ClaimRelevanceService:
    """Checks whether a matched fact-check is relevant to a user message using LLM.

    Handles content filter detection, retry logic, and fail-open semantics.
    Thread-safe and stateless beyond the injected LLMService dependency.

    The settings parameter allows callers to inject their own module-scoped
    settings reference, enabling existing test patches to work transparently.
    When not provided, the global settings singleton is used.
    """

    def __init__(self, llm_service: LLMService | None, settings: Any = None) -> None:
        self.llm_service = llm_service
        self._settings = settings if settings is not None else default_settings

    async def check_relevance(
        self,
        db: AsyncSession,
        original_message: str,
        matched_content: str,
        matched_source: str | None,
    ) -> tuple[RelevanceOutcome, str]:
        """Check if matched content is relevant to the original message using LLM.

        Detects content filter responses and retries without fact-check content
        to distinguish between problematic user messages and problematic fact-checks.

        Args:
            db: Database session (required by LLMService.complete)
            original_message: The user's original message
            matched_content: The matched fact-check content
            matched_source: Optional source URL

        Returns:
            Tuple of (RelevanceOutcome, reasoning):
            - RELEVANT: Match is relevant, should flag
            - NOT_RELEVANT: Match not relevant, don't flag
            - INDETERMINATE: Couldn't determine relevance (timeout, validation error,
              general error, or fact-check triggered filter). Returns INDETERMINATE
              so the tighter threshold is applied, filtering low-confidence matches.
            - CONTENT_FILTERED: User message itself triggered filter
        """
        cfg = self._settings

        if not cfg.RELEVANCE_CHECK_ENABLED:
            relevance_check_total.labels(
                outcome="disabled", decision="skipped", instance_id=cfg.INSTANCE_ID
            ).inc()
            return (RelevanceOutcome.RELEVANT, "Relevance check disabled")

        if not self.llm_service:
            logger.warning("LLM service not configured for relevance check")
            relevance_check_total.labels(
                outcome="not_configured", decision="fail_open", instance_id=cfg.INSTANCE_ID
            ).inc()
            return (RelevanceOutcome.INDETERMINATE, "LLM service not configured")

        start_time = time.monotonic()

        try:
            if cfg.RELEVANCE_CHECK_USE_OPTIMIZED_PROMPT:
                system_prompt, user_prompt = get_optimized_prompts(
                    message=original_message,
                    fact_check_title=matched_content[:100],
                    fact_check_content=matched_content,
                    source_url=matched_source,
                )
            else:
                source_info = f"\nSource: {matched_source}" if matched_source else ""

                system_prompt = """You are a relevance checker. Determine if a reference can meaningfully fact-check or provide context for a SPECIFIC CLAIM in the user's message.

IMPORTANT: The message must contain a verifiable claim or assertion. Simple mentions of people, topics, or questions are NOT claims.

Examples:
- "how about biden" → No claim, just a name mention → NOT RELEVANT (confidence: 0.99)
- "or donald trump" → No claim, just a name → NOT RELEVANT (confidence: 0.99)
- "Biden was a Confederate soldier" → Specific false claim → RELEVANT (confidence: 0.95)
- "Trump's sons shot endangered animals" → Verifiable claim → RELEVANT (confidence: 0.90)
- "What about the vaccine?" → Question, not a claim → NOT RELEVANT (confidence: 0.98)
- "The vaccine causes autism" → Specific claim that can be fact-checked → RELEVANT (confidence: 0.92)

Respond with JSON: {"is_relevant": true/false, "reasoning": "brief explanation", "confidence": 0.0-1.0}"""

                user_prompt = f"""User message: {original_message}

Reference: {matched_content}{source_info}

Step 1: Does the user message contain a specific claim or assertion (not just a topic mention or question)?
Step 2: If YES to step 1, can this reference fact-check or verify that specific claim?
Step 3: How confident are you in this assessment? (0.0 = uncertain, 1.0 = certain)

Only answer RELEVANT if BOTH steps are YES. Include your confidence score in the response."""

            messages = [
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=user_prompt),
            ]

            response = await asyncio.wait_for(
                self.llm_service.complete(
                    db=db,
                    messages=messages,
                    community_server_id=None,
                    model=cfg.RELEVANCE_CHECK_MODEL,
                    max_tokens=cfg.RELEVANCE_CHECK_MAX_TOKENS,
                    temperature=0.0,
                    response_format=RelevanceCheckResult,
                ),
                timeout=cfg.RELEVANCE_CHECK_TIMEOUT,
            )

            if response.finish_reason == "content_filter":
                latency_ms = (time.monotonic() - start_time) * 1000
                logger.warning(
                    "Content filter triggered during relevance check, retrying without fact-check",
                    extra={
                        "original_message_length": len(original_message),
                        "matched_content_length": len(matched_content),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                return await self._retry_without_fact_check(db, original_message, start_time)

            result = RelevanceCheckResult.model_validate_json(response.content)

            latency_ms = (time.monotonic() - start_time) * 1000
            logger.info(
                "Relevance check completed",
                extra={
                    "relevance_check_passed": result.is_relevant,
                    "relevance_reasoning": result.reasoning,
                    "relevance_confidence": result.confidence,
                    "latency_ms": round(latency_ms, 2),
                },
            )

            if not result.is_relevant:
                logger.debug(
                    "Content filtered by relevance check",
                    extra={
                        "outcome": "not_relevant",
                        "reasoning": result.reasoning,
                        "confidence": result.confidence,
                        "latency_ms": round(latency_ms, 2),
                    },
                )

            decision = "flagged" if result.is_relevant else "filtered"
            relevance_check_total.labels(
                outcome="success", decision=decision, instance_id=cfg.INSTANCE_ID
            ).inc()

            outcome = (
                RelevanceOutcome.RELEVANT if result.is_relevant else RelevanceOutcome.NOT_RELEVANT
            )
            return (outcome, result.reasoning)

        except Exception as e:
            return self._handle_check_error(e, start_time, cfg)

    def _handle_check_error(
        self,
        error: Exception,
        start_time: float,
        cfg: Any,
    ) -> tuple[RelevanceOutcome, str]:
        """Map check_relevance exceptions to INDETERMINATE outcomes with metrics."""
        latency_ms = (time.monotonic() - start_time) * 1000

        if isinstance(error, TimeoutError):
            metric_outcome = "timeout"
            message = f"Relevance check timed out after {cfg.RELEVANCE_CHECK_TIMEOUT}s"
            log_extra = {
                "timeout_seconds": cfg.RELEVANCE_CHECK_TIMEOUT,
                "latency_ms": round(latency_ms, 2),
            }
        elif isinstance(error, ValidationError):
            metric_outcome = "validation_error"
            message = f"Relevance check validation failed: {error}"
            log_extra = {
                "validation_error": str(error),
                "latency_ms": round(latency_ms, 2),
            }
        else:
            metric_outcome = "error"
            message = f"Relevance check failed: {error}"
            log_extra = {
                "error": str(error),
                "error_type": type(error).__name__,
                "latency_ms": round(latency_ms, 2),
            }

        logger.warning(
            f"Relevance check {metric_outcome}, returning indeterminate for tighter threshold",
            extra=log_extra,
        )
        relevance_check_total.labels(
            outcome=metric_outcome,
            decision="fail_open_indeterminate",
            instance_id=cfg.INSTANCE_ID,
        ).inc()
        return (RelevanceOutcome.INDETERMINATE, message)

    async def _retry_without_fact_check(
        self,
        db: AsyncSession,
        original_message: str,
        start_time: float,
    ) -> tuple[RelevanceOutcome, str]:
        """Retry relevance check with only the user message to isolate content filter source.

        Called when the initial relevance check triggers a content filter. By retrying
        with only the user's message (no fact-check content), we can determine:
        - If retry also triggers filter: user's message contains problematic content
        - If retry succeeds: fact-check content was the problem, treat as indeterminate

        Args:
            db: Database session
            original_message: The user's original message (without fact-check content)
            start_time: Start time of the original check for latency tracking

        Returns:
            Tuple of (RelevanceOutcome, reasoning):
            - CONTENT_FILTERED: User message itself triggers content filter
            - INDETERMINATE: Fact-check content was the issue, can't determine relevance
        """
        if not self.llm_service:
            return (
                RelevanceOutcome.INDETERMINATE,
                "LLM service not configured for retry",
            )

        cfg = self._settings

        simplified_system_prompt = """Analyze this message for factual claims.
Respond with JSON: {"has_claims": true/false, "reasoning": "brief explanation"}"""

        messages = [
            LLMMessage(role="system", content=simplified_system_prompt),
            LLMMessage(role="user", content=original_message),
        ]

        try:
            response = await asyncio.wait_for(
                self.llm_service.complete(
                    db=db,
                    messages=messages,
                    community_server_id=None,
                    model=cfg.RELEVANCE_CHECK_MODEL,
                    max_tokens=cfg.RELEVANCE_CHECK_MAX_TOKENS,
                    temperature=0.0,
                ),
                timeout=cfg.RELEVANCE_CHECK_TIMEOUT,
            )

            latency_ms = (time.monotonic() - start_time) * 1000

            if response.finish_reason == "content_filter":
                logger.warning(
                    "Content filter triggered on user message alone",
                    extra={
                        "message_length": len(original_message),
                        "latency_ms": round(latency_ms, 2),
                    },
                )
                relevance_check_total.labels(
                    outcome="content_filter",
                    decision="message_filtered",
                    instance_id=cfg.INSTANCE_ID,
                ).inc()
                return (
                    RelevanceOutcome.CONTENT_FILTERED,
                    "Message content triggered safety filter",
                )

            if response.finish_reason == "stop":
                log_level = "info"
                log_message = "Retry succeeded - fact-check content triggered original filter"
                metric_outcome = "content_filter"
                reasoning = "Fact-check content triggered safety filter; relevance indeterminate"
            elif response.finish_reason == "length":
                log_level = "warning"
                log_message = "Retry response truncated (max_tokens reached)"
                metric_outcome = "content_filter_retry_truncated"
                reasoning = "Retry response truncated; relevance indeterminate"
            else:
                log_level = "warning"
                log_message = "Unexpected finish_reason in retry response"
                metric_outcome = "content_filter_retry_unexpected"
                reasoning = (
                    f"Unexpected finish_reason: {response.finish_reason}; relevance indeterminate"
                )

            log_fn = logger.info if log_level == "info" else logger.warning
            log_fn(
                log_message,
                extra={
                    "message_length": len(original_message),
                    "latency_ms": round(latency_ms, 2),
                    "finish_reason": response.finish_reason,
                },
            )
            relevance_check_total.labels(
                outcome=metric_outcome,
                decision="factcheck_filtered"
                if response.finish_reason == "stop"
                else "indeterminate",
                instance_id=cfg.INSTANCE_ID,
            ).inc()
            return (RelevanceOutcome.INDETERMINATE, reasoning)

        except TimeoutError:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Retry timed out, treating as indeterminate",
                extra={
                    "timeout_seconds": cfg.RELEVANCE_CHECK_TIMEOUT,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="content_filter_retry_timeout",
                decision="indeterminate",
                instance_id=cfg.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Retry timed out after {cfg.RELEVANCE_CHECK_TIMEOUT}s",
            )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(
                "Retry failed, treating as indeterminate",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "latency_ms": round(latency_ms, 2),
                },
            )
            relevance_check_total.labels(
                outcome="content_filter_retry_error",
                decision="indeterminate",
                instance_id=cfg.INSTANCE_ID,
            ).inc()
            return (
                RelevanceOutcome.INDETERMINATE,
                f"Retry failed: {e}",
            )
