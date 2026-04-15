"""Regression test for pydantic-ai v1.80 retry-counter behavior change.

v1.80 changed retry accounting so that unknown tool calls from the model no
longer exhaust the global retry counter, and output validators observe the
correct remaining retry budget.

Release reference (pydantic-ai 1.80.0):
  "Unknown tool calls no longer exhaust the global retry counter; output
  validators see the right counter."

``claim_relevance_check`` uses ``pydantic_ai`` (both the ``Agent`` wrapper and
``pydantic_ai.direct.model_request``). This test guards the agent-level retry
accounting contract that the service relies on. A regression here would cause
production ``RelevanceCheckResult`` runs to spuriously fail with
``UsageLimitExceeded`` / retry-exhausted errors when the model emits a
hallucinated tool call before producing a valid structured response.
"""

from __future__ import annotations

from typing import cast

import pytest
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


@pytest.mark.asyncio
async def test_unknown_tool_call_does_not_exhaust_retry_counter() -> None:
    """Unknown tool calls must not consume the global retry budget (pydantic-ai v1.80+).

    Scenario with ``retries=1``:
      1. Model emits a hallucinated tool call (unknown tool name).
      2. Model emits text that the output validator rejects with ``ModelRetry``.
      3. Model emits valid text that passes the validator.

    Pre-v1.80 behaviour: step 1 would consume the single retry, so step 2's
    ``ModelRetry`` would push the agent over budget and the run would fail.

    v1.80+ behaviour: step 1 does not count; the validator's single retry
    succeeds and the run returns step 3's output.
    """
    agent: Agent[None, str] = Agent(output_type=str, retries=1)

    validator_calls = {"n": 0}

    @agent.output_validator
    def reject_first_then_accept(data: str) -> str:
        validator_calls["n"] += 1
        if data == "needs-retry":
            raise ModelRetry("validator asked for one retry")
        return data

    model_calls = {"n": 0}

    def function_model(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        model_calls["n"] += 1
        if model_calls["n"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="definitely_not_a_registered_tool",
                        args={"q": "unused"},
                        tool_call_id="hallucinated-1",
                    )
                ]
            )
        if model_calls["n"] == 2:
            return ModelResponse(parts=[TextPart(content="needs-retry")])
        return ModelResponse(parts=[TextPart(content="final-valid")])

    result = await agent.run("prompt", model=FunctionModel(function_model))

    assert cast(str, result.output) == "final-valid"
    assert model_calls["n"] == 3
    assert validator_calls["n"] == 2
