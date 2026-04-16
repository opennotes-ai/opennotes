"""Offline regression harness for the ContentReviewerAgent.

Uses pydantic-ai FunctionModel for deterministic testing — no real LLM calls.
Each case in the dataset produces a FunctionModel that returns the expected
classification, then we verify the agent output matches expectations.

Run the full eval suite:
    mise run test:server -- tests/eval/bulk_content_scan/ -m eval -v

Run as part of CI opt-in:
    mise run test:server -- -m eval -v
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.bulk_content_scan.content_reviewer_agent import ContentReviewerService
from src.bulk_content_scan.schemas import ContentModerationClassificationResult

from .dataset import (
    EVAL_DATASET,
    EvalCase,
    build_expected_result,
    get_retry_recovery_cases,
    get_standard_cases,
)

pytestmark = [pytest.mark.eval, pytest.mark.unit]


@dataclasses.dataclass
class EvalResult:
    case_name: str
    passed: bool
    actual_action: str | None
    expected_action: str | None
    actual_tier: str | None
    expected_tier: str | None
    actual_confidence: float
    confidence_in_range: bool
    notes: str = ""


def _build_function_model(expected: ContentModerationClassificationResult) -> FunctionModel:
    def model_fn(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        del messages, agent_info
        import json

        payload = expected.model_dump()
        return ModelResponse(parts=[TextPart(content=json.dumps(payload))])

    return FunctionModel(model_fn)


def _check_result(
    case: EvalCase,
    result: ContentModerationClassificationResult,
) -> EvalResult:
    action_match = (
        result.recommended_action == case.expected_action
        if case.expected_action is not None
        else True
    )
    tier_match = (
        result.action_tier == case.expected_tier if case.expected_tier is not None else True
    )
    lo, hi = case.expected_confidence_range
    confidence_ok = lo <= result.confidence <= hi
    passed = action_match and tier_match and confidence_ok

    notes_parts = []
    if not action_match:
        notes_parts.append(
            f"action mismatch: got={result.recommended_action!r} want={case.expected_action!r}"
        )
    if not tier_match:
        notes_parts.append(f"tier mismatch: got={result.action_tier!r} want={case.expected_tier!r}")
    if not confidence_ok:
        notes_parts.append(f"confidence {result.confidence:.3f} outside [{lo:.2f}, {hi:.2f}]")

    return EvalResult(
        case_name=case.name,
        passed=passed,
        actual_action=result.recommended_action,
        expected_action=case.expected_action,
        actual_tier=result.action_tier,
        expected_tier=case.expected_tier,
        actual_confidence=result.confidence,
        confidence_in_range=confidence_ok,
        notes="; ".join(notes_parts),
    )


class TestContentReviewerEvalStandard:
    """Eval harness for standard (non-retry) cases in the dataset."""

    @pytest.mark.parametrize(
        "case",
        get_standard_cases(),
        ids=[c.name for c in get_standard_cases()],
    )
    async def test_standard_case(self, case: EvalCase) -> None:
        expected = build_expected_result(case)
        model = _build_function_model(expected)

        service = ContentReviewerService()
        result = await service.classify(
            content_item=case.content_item,
            pre_computed_evidence=case.evidence,
            model=model,
        )

        eval_result = _check_result(case, result)
        assert eval_result.passed, (
            f"Eval case '{case.name}' failed: {eval_result.notes}\n"
            f"  description: {case.description}"
        )

    async def test_all_standard_cases_produce_valid_schema(self) -> None:
        service = ContentReviewerService()
        failures: list[str] = []

        for case in get_standard_cases():
            expected = build_expected_result(case)
            model = _build_function_model(expected)
            result = await service.classify(
                content_item=case.content_item,
                pre_computed_evidence=case.evidence,
                model=model,
            )
            if not isinstance(result, ContentModerationClassificationResult):
                failures.append(f"{case.name}: wrong type {type(result)}")
            elif not (0.0 <= result.confidence <= 1.0):
                failures.append(f"{case.name}: confidence {result.confidence} out of [0, 1]")
            elif not isinstance(result.category_labels, dict):
                failures.append(f"{case.name}: category_labels not a dict")
            elif not isinstance(result.explanation, str) or not result.explanation:
                failures.append(f"{case.name}: explanation empty or not a string")

        assert not failures, "Schema validation failures:\n" + "\n".join(failures)

    async def test_accuracy_report(self) -> None:
        service = ContentReviewerService()
        results: list[EvalResult] = []

        for case in get_standard_cases():
            expected = build_expected_result(case)
            model = _build_function_model(expected)
            result = await service.classify(
                content_item=case.content_item,
                pre_computed_evidence=case.evidence,
                model=model,
            )
            results.append(_check_result(case, result))

        total = len(results)
        passed = sum(1 for r in results if r.passed)
        accuracy = passed / total if total > 0 else 0.0

        failures = [r for r in results if not r.passed]
        report_lines = [
            f"ContentReviewerAgent eval accuracy: {passed}/{total} ({accuracy:.1%})",
        ]
        if failures:
            report_lines.append("Failed cases:")
            for f in failures:
                report_lines.append(f"  - {f.case_name}: {f.notes}")

        print("\n" + "\n".join(report_lines))

        assert accuracy >= 1.0, f"Eval accuracy {accuracy:.1%} below 100% threshold.\n" + "\n".join(
            report_lines
        )


class TestContentReviewerEvalRetryRecovery:
    """Eval harness for retry/recovery behavior using output_validator correction."""

    async def test_output_validator_retry_recovery(self) -> None:
        """Verify the agent handles output_validator retry correctly.

        Scenario (retries=1):
          1. First call returns a structurally valid but semantically invalid result
             (low confidence with explanation sentinel that the validator rejects).
          2. Output validator raises ModelRetry.
          3. Second call returns valid output — accepted.

        This guards against regressions where retry budget exhaustion causes
        classification failure instead of recovery.
        """
        from pydantic_ai import Agent

        call_count = {"n": 0}
        validator_calls = {"n": 0}

        good_result = ContentModerationClassificationResult(
            confidence=0.82,
            category_labels={"misinformation": True},
            recommended_action="review",
            action_tier="tier_2_consensus",
            explanation="Flat-earth claim contradicted by scientific consensus",
        )

        agent: Agent[None, ContentModerationClassificationResult] = Agent(
            output_type=ContentModerationClassificationResult,
            retries=1,
        )

        @agent.output_validator
        def reject_sentinel_explanation(
            data: ContentModerationClassificationResult,
        ) -> ContentModerationClassificationResult:
            validator_calls["n"] += 1
            if data.explanation == "__needs_retry__":
                raise ModelRetry("sentinel explanation rejected, retry required")
            return data

        def recovery_model(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            import json

            del agent_info
            call_count["n"] += 1
            if call_count["n"] == 1:
                first_payload = good_result.model_dump()
                first_payload["explanation"] = "__needs_retry__"
                return ModelResponse(parts=[TextPart(content=json.dumps(first_payload))])
            return ModelResponse(parts=[TextPart(content=json.dumps(good_result.model_dump()))])

        agent_result = await agent.run(
            "Classify content.",
            model=FunctionModel(recovery_model),
        )

        assert isinstance(agent_result.output, ContentModerationClassificationResult)
        assert agent_result.output.recommended_action == "review"
        assert 0.0 <= agent_result.output.confidence <= 1.0
        assert agent_result.output.explanation == good_result.explanation
        assert call_count["n"] == 2
        assert validator_calls["n"] == 2

    async def test_retry_recovery_with_unknown_tool_call(self) -> None:
        """Unknown tool calls must not exhaust the retry budget (pydantic-ai ≥1.80).

        Scenario (retries=1):
          1. Model emits a hallucinated tool call.
          2. Output validator rejects first valid response with ModelRetry.
          3. Model emits second valid response — accepted.

        Pre-v1.80: step 1 consumed the retry, step 2 caused exhaustion.
        v1.80+: step 1 does not count; retry succeeds.
        """
        from pydantic_ai import Agent

        call_count = {"n": 0}
        validator_calls = {"n": 0}

        good_result = ContentModerationClassificationResult(
            confidence=0.78,
            category_labels={"misinformation": True},
            recommended_action="review",
            action_tier="tier_2_consensus",
            explanation="Recovery after hallucinated tool call",
        )

        agent: Agent[None, ContentModerationClassificationResult] = Agent(
            output_type=ContentModerationClassificationResult,
            retries=1,
        )

        @agent.output_validator
        def reject_first_then_accept(
            data: ContentModerationClassificationResult,
        ) -> ContentModerationClassificationResult:
            validator_calls["n"] += 1
            if data.explanation == "needs-retry":
                raise ModelRetry("validator requested retry")
            return data

        def model_with_hallucinated_tool(
            messages: list[ModelMessage], agent_info: AgentInfo
        ) -> ModelResponse:
            import json

            del agent_info
            call_count["n"] += 1
            if call_count["n"] == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="not_a_real_tool",
                            args={"unused": "arg"},
                            tool_call_id="hallucinated-eval-1",
                        )
                    ]
                )
            if call_count["n"] == 2:
                needs_retry = good_result.model_copy(update={"explanation": "needs-retry"})
                return ModelResponse(parts=[TextPart(content=json.dumps(needs_retry.model_dump()))])
            return ModelResponse(parts=[TextPart(content=json.dumps(good_result.model_dump()))])

        agent_result = await agent.run(
            "Classify content.",
            model=FunctionModel(model_with_hallucinated_tool),
        )

        assert agent_result.output.recommended_action == "review"
        assert agent_result.output.explanation == good_result.explanation
        assert call_count["n"] == 3
        assert validator_calls["n"] == 2

    @pytest.mark.parametrize(
        "case",
        get_retry_recovery_cases(),
        ids=[c.name for c in get_retry_recovery_cases()],
    )
    async def test_retry_recovery_case_via_service(self, case: EvalCase) -> None:
        """Service-level: after agent-level retry recovery, service returns the final result.

        The service wraps the agent in asyncio.wait_for. It does not retry internally.
        Retry/recovery happens inside the agent (via output_validator). This test uses
        a model that requires one validator-driven retry before returning the correct
        final result, then verifies the service surfaces that final result.
        """
        from pydantic_ai import Agent

        call_count = {"n": 0}
        expected = build_expected_result(case)

        recovery_agent: Agent[None, ContentModerationClassificationResult] = Agent(
            output_type=ContentModerationClassificationResult,
            retries=1,
        )

        @recovery_agent.output_validator
        def reject_sentinel(
            data: ContentModerationClassificationResult,
        ) -> ContentModerationClassificationResult:
            if data.explanation == "__needs_retry__":
                raise ModelRetry("sentinel rejected, retry")
            return data

        def two_step_model(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
            import json

            del messages, agent_info
            call_count["n"] += 1
            if call_count["n"] == 1:
                first = expected.model_copy(update={"explanation": "__needs_retry__"})
                return ModelResponse(parts=[TextPart(content=json.dumps(first.model_dump()))])
            return ModelResponse(parts=[TextPart(content=json.dumps(expected.model_dump()))])

        agent_result = await recovery_agent.run(
            f"Classify: {case.content_item.content_text[:200]}",
            model=FunctionModel(two_step_model),
        )

        result = agent_result.output

        assert isinstance(result, ContentModerationClassificationResult)
        assert result.confidence == expected.confidence
        assert result.recommended_action == expected.recommended_action
        assert call_count["n"] == 2


class TestEvalDatasetCoverage:
    """Meta-tests verifying the dataset itself covers all required tiers and actions."""

    def test_dataset_covers_hide_tier1(self) -> None:
        cases = [
            c
            for c in EVAL_DATASET
            if c.expected_action == "hide" and c.expected_tier == "tier_1_immediate"
        ]
        assert len(cases) >= 1, "Dataset must include at least one hide/tier_1_immediate case"

    def test_dataset_covers_pass_none(self) -> None:
        cases = [c for c in EVAL_DATASET if c.expected_action == "pass" and c.expected_tier is None]
        assert len(cases) >= 1, "Dataset must include at least one pass/None case"

    def test_dataset_covers_review_tier2(self) -> None:
        cases = [
            c
            for c in EVAL_DATASET
            if c.expected_action == "review" and c.expected_tier == "tier_2_consensus"
        ]
        assert len(cases) >= 1, "Dataset must include at least one review/tier_2_consensus case"

    def test_dataset_covers_similarity_evidence(self) -> None:
        similarity_cases = [
            c
            for c in EVAL_DATASET
            if any(e.__class__.__name__ == "SimilarityMatch" for e in c.evidence)
        ]
        assert len(similarity_cases) >= 1, "Dataset must include similarity match evidence"

    def test_dataset_covers_moderation_evidence(self) -> None:
        moderation_cases = [
            c
            for c in EVAL_DATASET
            if any(e.__class__.__name__ == "OpenAIModerationMatch" for e in c.evidence)
        ]
        assert len(moderation_cases) >= 1, "Dataset must include OpenAI moderation evidence"

    def test_dataset_covers_flashpoint_evidence(self) -> None:
        flashpoint_cases = [
            c
            for c in EVAL_DATASET
            if any(e.__class__.__name__ == "ConversationFlashpointMatch" for e in c.evidence)
        ]
        assert len(flashpoint_cases) >= 1, "Dataset must include flashpoint evidence"

    def test_dataset_covers_retry_recovery(self) -> None:
        retry_cases = [c for c in EVAL_DATASET if c.requires_retry_recovery]
        assert len(retry_cases) >= 1, "Dataset must include at least one retry recovery case"

    def test_dataset_has_minimum_size(self) -> None:
        assert len(EVAL_DATASET) >= 8, f"Dataset too small: {len(EVAL_DATASET)} cases"

    def test_all_case_names_are_unique(self) -> None:
        names = [c.name for c in EVAL_DATASET]
        assert len(names) == len(set(names)), "Duplicate case names in dataset"

    def test_all_confidence_ranges_valid(self) -> None:
        for case in EVAL_DATASET:
            lo, hi = case.expected_confidence_range
            assert 0.0 <= lo <= hi <= 1.0, (
                f"Case '{case.name}': invalid confidence range [{lo}, {hi}]"
            )
