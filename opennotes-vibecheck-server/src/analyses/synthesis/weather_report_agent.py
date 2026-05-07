"""Weather-report evaluator for post-coverage synthesis.

The evaluator is grounded in the same social epistemology stack as the
headline layer: truth as source construction (Potter 1996; Sacks 1972; Fisher 1984),
framing and conversational accountability (Goffman 1974; Gumperz 1982),
and affective stance attribution (Biber & Finegan 1989; DuBois 2007;
Brown & Levinson 1987).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from src.analyses.claims._claims_schemas import ClaimsReport
from src.analyses.opinions._highlights_schemas import OpinionsHighlightsReport
from src.analyses.opinions._schemas import SentimentStatsReport, SubjectiveClaim
from src.analyses.opinions._trends_schemas import TrendsOppositionsReport
from src.analyses.schemas import PageKind
from src.analyses.synthesis._weather_schemas import WeatherAxis, WeatherReport
from src.analyses.tone._flashpoint_schemas import FlashpointMatch
from src.analyses.tone._scd_schemas import SCDReport
from src.config import Settings
from src.services.gemini_agent import (
    GoogleLogprobs,
    build_agent,
    extract_google_logprobs,
    run_vertex_agent_with_retry,
)
from src.services.vertex_limiter import vertex_slot

WEATHER_SYSTEM_PROMPT = """You synthesize a weather-style report with three axes:
`truth`, `relevance`, and `sentiment`, each as a single label choice with
optional confidence.

Use grounded evidence where possible, but treat personal testimony and lived
experience as `self_reported` on truth unless there are explicit, externally
verifiable factual claims that materially change the conclusion. This keeps
experiential content from becoming `misleading` by default.

Guiding lens:
- Knowledge Construction Infrastructure (Potter 1996, Sacks 1972, Fisher 1984): how claims
  are socially built, indexed, and checked.
- Frame Management (Goffman 1974, Gumperz 1982): role-taking, indexical framing, and
  participation structure.
- Affective Stance (Biber & Finegan 1989, DuBois 2007, Brown & Levinson 1987):
  how affect colors evidence presentation.

Rules for truth:
- `self_reported` when a thread is primarily testimonial, first-person, or
  experience-based.
- `sourced` / `mostly_factual` when the page provides verifiable external
  references or multiple explicit factual anchors.
- `hearsay` when claims are repeated or attributed but remain thinly evidenced.
- `misleading` when supported evidence is directly contradicted or strongly
  likely false.

Few-shot fixtures:
1) Self-reporting fixture
input: {
  "transcript_excerpt": "I was sick after this, then rested more and felt better. This is what happened to me personally."
}
output: {
  "truth": {"label": "self_reported"},
  "relevance": {"label": "on_topic"},
  "sentiment": {"label": "supportive"}
}

2) Mixed sourced + self-reported fixture
input: {
  "transcript_excerpt": "A clinical report at https://example.edu/notes says sleep improves mood. I tried that routine and it helped me feel calmer."
}
output: {
  "truth": {"label": "self_reported"},
  "relevance": {"label": "on_topic"},
  "sentiment": {"label": "supportive"}
}

Output label must be one of:
truth: sourced | mostly_factual | self_reported | hearsay | misleading
relevance: insightful | on_topic | chatty | drifting | off_topic
sentiment: free-form stance token such as supportive, neutral, critical, oppositional

Use JSON only. Return a strict `WeatherReport` object."""


@dataclass
class WeatherInputs:
    page_title: str | None
    page_kind: PageKind
    transcript_excerpt: str
    claims_report: ClaimsReport | None
    highlights: OpinionsHighlightsReport | None
    trends_oppositions: TrendsOppositionsReport | None
    sentiment_stats: SentimentStatsReport | None
    subjective_claims: list[SubjectiveClaim]
    flashpoint_matches: list[FlashpointMatch]
    scd: SCDReport | None
    unavailable_inputs: list[str] = field(default_factory=list)


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _serialize_inputs(inputs: WeatherInputs) -> str:
    payload = {
        "page_title": inputs.page_title,
        "page_kind": inputs.page_kind.value,
        "transcript_excerpt": inputs.transcript_excerpt,
        "claims_report": _model_dump(inputs.claims_report)
        if inputs.claims_report is not None
        else None,
        "highlights": _model_dump(inputs.highlights)
        if inputs.highlights is not None
        else None,
        "trends_oppositions": _model_dump(inputs.trends_oppositions)
        if inputs.trends_oppositions is not None
        else None,
        "sentiment_stats": _model_dump(inputs.sentiment_stats)
        if inputs.sentiment_stats is not None
        else None,
        "subjective_claims": [_model_dump(claim) for claim in inputs.subjective_claims],
        "flashpoint_matches": [_model_dump(match) for match in inputs.flashpoint_matches],
        "scd": _model_dump(inputs.scd) if inputs.scd is not None else None,
        "unavailable_inputs": list(inputs.unavailable_inputs),
    }
    return json.dumps(payload)


def _coerce_logprob(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _axis_with_empty_alternatives(label: Any, logprob: float | None) -> WeatherAxis[Any]:
    return WeatherAxis[Any](label=label, logprob=logprob, alternatives=[])


def _attach_logprobs(
    report: WeatherReport,
    metadata: GoogleLogprobs | None,
) -> WeatherReport:
    # Google/pydantic-ai returns logprob metadata at the output level only;
    # there is no reliable per-axis path today.
    avg_logprob = _coerce_logprob(metadata.get("avg_logprobs")) if metadata else None
    if avg_logprob is None:
        return WeatherReport(
            truth=_axis_with_empty_alternatives(report.truth.label, None),
            relevance=_axis_with_empty_alternatives(report.relevance.label, None),
            sentiment=_axis_with_empty_alternatives(report.sentiment.label, None),
        )

    # Best-effort coarse confidence: copy output-level score to all axes.
    # v1 keeps `alternatives=[]` until a dependable alternatives mapping exists.
    return WeatherReport(
        truth=_axis_with_empty_alternatives(report.truth.label, avg_logprob),
        relevance=_axis_with_empty_alternatives(report.relevance.label, avg_logprob),
        sentiment=_axis_with_empty_alternatives(report.sentiment.label, avg_logprob),
    )


async def evaluate_weather(
    inputs: WeatherInputs,
    settings: Settings,
    *,
    job_id: UUID,
) -> WeatherReport:
    """Run the weather-report synthesis agent and return a structured
    `WeatherReport`.
    """
    del job_id
    agent = cast(
        Any,
        build_agent(
            settings,
            output_type=WeatherReport,
            system_prompt=WEATHER_SYSTEM_PROMPT,
            name="vibecheck.weather_report",
            tier="synthesis",
        ),
    )
    async with vertex_slot(settings):
        result = await run_vertex_agent_with_retry(agent, _serialize_inputs(inputs))

    model_output = cast(WeatherReport, result.output)
    logprobs = extract_google_logprobs(result)
    return _attach_logprobs(model_output, logprobs)
