"""Tests for facts_agent.py — pydantic-ai Agent wrapping check_known_misinformation.

All tests use fake agents (monkeypatching build_agent) — no Vertex calls.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from src.analyses.claims._claims_schemas import ClaimsReport, DedupedClaim
from src.analyses.claims._factcheck_schemas import FactCheckMatch
from src.analyses.claims.known_misinfo import check_known_misinformation
from src.config import Settings


# ---------------------------------------------------------------------------
# Fake agent infrastructure
# ---------------------------------------------------------------------------


@dataclass
class _FakeRunResult:
    output: list[FactCheckMatch]


@dataclass
class _FakeAgent:
    """Minimal fake mimicking the pydantic-ai Agent surface used by facts_agent."""

    output: list[FactCheckMatch] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    tool_funcs: dict[str, Any] = field(default_factory=dict)
    raise_on_run: BaseException | None = None

    def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
        if func is None:

            def _wrap(f: Any) -> Any:
                self.tool_funcs[getattr(f, "__name__", "?")] = f
                return f

            return _wrap
        self.tool_funcs[getattr(func, "__name__", "?")] = func
        return func

    async def run(self, user_prompt: str, *, deps: Any = None) -> _FakeRunResult:
        if self.raise_on_run is not None:
            raise self.raise_on_run
        self.prompts.append(user_prompt)
        return _FakeRunResult(output=self.output)


def _make_fake_agent(
    monkeypatch: pytest.MonkeyPatch,
    output: list[FactCheckMatch] | None = None,
    raise_on_run: BaseException | None = None,
) -> _FakeAgent:
    fake = _FakeAgent(
        output=output or [],
        raise_on_run=raise_on_run,
    )
    monkeypatch.setattr(
        "src.analyses.claims.facts_agent.build_agent",
        lambda settings, output_type=None, system_prompt=None: fake,
    )
    return fake


def _make_job_ids() -> tuple[Any, Any]:
    return uuid4(), uuid4()


def _settings() -> Settings:
    return Settings()


def _claims_report(*claim_texts: str) -> ClaimsReport:
    claims = [
        DedupedClaim(
            canonical_text=t,
            occurrence_count=1,
            author_count=1,
            utterance_ids=["u1"],
            representative_authors=["alice"],
        )
        for t in claim_texts
    ]
    return ClaimsReport(
        deduped_claims=claims,
        total_claims=len(claims),
        total_unique=len(claims),
    )


class _Payload:
    """Minimal payload stand-in carrying a claims_report attribute."""

    def __init__(self, claims_report: ClaimsReport | None = None) -> None:
        self.claims_report = claims_report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_claims_returns_empty_no_agent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC6: empty deduped_claims → short-circuit, no agent invocation."""
    fake = _make_fake_agent(monkeypatch)
    pool, job_id, task_attempt = None, *_make_job_ids()
    payload = _Payload(claims_report=_claims_report())

    from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo

    result = await run_facts_claims_known_misinfo(
        pool, job_id, task_attempt, payload, _settings()
    )

    assert result == {"known_misinformation": []}
    assert fake.prompts == []


@pytest.mark.asyncio
async def test_agent_receives_claims_as_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3/AC5: agent.run() is called with a JSON-serialised list of claims."""
    import json

    fake = _make_fake_agent(monkeypatch)
    pool, job_id, task_attempt = None, *_make_job_ids()
    payload = _Payload(claims_report=_claims_report("vaccines cause autism", "5G is dangerous"))

    from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo

    await run_facts_claims_known_misinfo(
        pool, job_id, task_attempt, payload, _settings()
    )

    assert len(fake.prompts) == 1
    parsed = json.loads(fake.prompts[0])
    assert isinstance(parsed, list)
    assert len(parsed) == 2


@pytest.mark.asyncio
async def test_tool_failure_returns_empty_list_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4: tool errors must not propagate — the tool returns [] on exception."""
    import httpx

    from src.analyses.claims.facts_agent import (
        FactsAgentDeps,
        run_facts_claims_known_misinfo,
    )

    def _raise_tool(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("tool exploded")

    captured_tool: dict[str, Any] = {}

    class _CapturingFakeAgent(_FakeAgent):
        def tool(self, func: Any = None, /, **_kwargs: Any) -> Any:
            result = super().tool(func, **_kwargs)
            if func is not None:
                captured_tool["func"] = func
            return result

    fake = _CapturingFakeAgent(output=[])
    monkeypatch.setattr(
        "src.analyses.claims.facts_agent.build_agent",
        lambda settings, output_type=None, system_prompt=None: fake,
    )
    monkeypatch.setattr(
        "src.analyses.claims.facts_agent.check_known_misinformation",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("tool exploded")),
    )

    pool, job_id, task_attempt = None, *_make_job_ids()
    payload = _Payload(claims_report=_claims_report("vaccines cause autism"))

    result = await run_facts_claims_known_misinfo(
        pool, job_id, task_attempt, payload, _settings()
    )

    assert result == {"known_misinformation": []}

    tool_fn = fake.tool_funcs.get("check_known_misinformation_tool")
    assert tool_fn is not None, "check_known_misinformation_tool not registered"

    class _FakeCtx:
        deps = FactsAgentDeps(httpx_client=None)  # type: ignore[arg-type]

    returned = await tool_fn(_FakeCtx(), "some claim")
    assert returned == []


@pytest.mark.asyncio
async def test_agent_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4: Vertex/agent errors must propagate (only tool errors are swallowed)."""
    _make_fake_agent(
        monkeypatch,
        raise_on_run=RuntimeError("vertex exploded"),
    )
    pool, job_id, task_attempt = None, *_make_job_ids()
    payload = _Payload(claims_report=_claims_report("some claim"))

    from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo

    with pytest.raises(RuntimeError, match="vertex exploded"):
        await run_facts_claims_known_misinfo(
            pool, job_id, task_attempt, payload, _settings()
        )


@pytest.mark.asyncio
async def test_matches_from_tool_appear_in_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: matches returned by the agent appear in the result dict."""
    matches = [
        FactCheckMatch(
            claim_text="vaccines cause autism",
            publisher="Snopes",
            review_title="Do vaccines cause autism?",
            review_url="https://snopes.com/fc/vaccines",
            textual_rating="False",
            review_date=date(2021, 2, 1),
        )
    ]
    _make_fake_agent(monkeypatch, output=matches)

    pool, job_id, task_attempt = None, *_make_job_ids()
    payload = _Payload(claims_report=_claims_report("vaccines cause autism"))

    from src.analyses.claims.facts_agent import run_facts_claims_known_misinfo

    result = await run_facts_claims_known_misinfo(
        pool, job_id, task_attempt, payload, _settings()
    )

    known = result["known_misinformation"]
    assert len(known) == 1
    assert known[0]["claim_text"] == "vaccines cause autism"
    assert known[0]["publisher"] == "Snopes"
    assert known[0]["textual_rating"] == "False"


def test_known_misinfo_signature_unchanged() -> None:
    """AC1/back-compat: check_known_misinformation must stay callable with
    (claim_text, *, httpx_client=...) — unchanged from before this task."""
    sig = inspect.signature(check_known_misinformation)
    params = sig.parameters

    assert "claim_text" in params, "claim_text positional param missing"
    assert "httpx_client" in params, "httpx_client keyword param missing"

    httpx_param = params["httpx_client"]
    assert httpx_param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ), "httpx_client should be keyword-accessible"
