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
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.llm_config.model_factory import build_url_scan_vertex_model
from src.llm_config.model_id import ModelId
from src.url_content_scan.analyses.synthesis.weather_report_schemas import WeatherReport
from src.url_content_scan.claims_schemas import ClaimsReport
from src.url_content_scan.observability import url_scan_instrumentation
from src.url_content_scan.opinions_schemas import (
    OpinionsHighlightsReport,
    SentimentStatsReport,
    SubjectiveClaim,
    TrendsOppositionsReport,
)
from src.url_content_scan.schemas import PageKind
from src.url_content_scan.tone_schemas import FlashpointMatch, SCDReport

if TYPE_CHECKING:
    from src.config import Settings

DEFAULT_WEATHER_MODEL = "google-vertex:gemini-3.1-pro-preview"

WEATHER_SYSTEM_PROMPT = """You synthesize a weather-style report with three axes:
`truth`, `relevance`, and `sentiment`, each as a single label choice with
optional confidence.

Use grounded evidence where possible, but treat personal testimony and lived
experience as `first_person` on truth unless the discussion shifts into broader
factual claims. This keeps experiential content categorized by how the speaker
holds the knowledge, not by whether the experience can be externally verified.

Guiding lens:
- Knowledge Construction Infrastructure (Potter 1996, Sacks 1972, Fisher 1984): how claims
  are socially built, indexed, and checked.
- Frame Management (Goffman 1974, Gumperz 1982): role-taking, indexical framing, and
  participation structure.
- Affective Stance (Biber & Finegan 1989, DuBois 2007, Brown & Levinson 1987):
  how affect colors evidence presentation.

Rules for truth:
- `sourced` when factual claims are held with visible external references,
  links, citations, or concrete attribution.
- `factual_claims` when claims are factual in nature but are presented without
  visible sourcing. This labels the claim type and provenance, not whether the
  claim is ultimately right.
- `first_person` when the speaker presents their own first-person experience,
  testimony, or direct personal account.
- `hearsay` when claims are passed along second-hand without direct grounding.
- `misleading` when the speaker actively distorts provenance, strategically
  omits what is known, or obscures how the knowledge is held.

Few-shot fixtures:
1) First-person fixture
input: {
  "transcript_excerpt": "I was sick after this, then rested more and felt better. This is what happened to me personally."
}
output: {
  "truth": {"label": "first_person"},
  "relevance": {"label": "on_topic"},
  "sentiment": {"label": "supportive"}
}

2) Mixed sourced + first-person fixture
input: {
  "transcript_excerpt": "A clinical report at https://example.edu/notes says sleep improves mood. I tried that routine and it helped me feel calmer."
}
output: {
  "truth": {"label": "first_person"},
  "relevance": {"label": "on_topic"},
  "sentiment": {"label": "supportive"}
}

When trends/oppositions data is available, incorporate recurring patterns and
opposing camps into your truth and relevance assessment.
When highlights are available, weight dominant high-influence claims more heavily.

Output label must be one of:
truth: sourced | factual_claims | first_person | hearsay | misleading
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
        "highlights": _model_dump(inputs.highlights) if inputs.highlights is not None else None,
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


weather_report_agent: Agent[None, WeatherReport] = Agent(
    name="url-content-scan-weather-report",
    output_type=WeatherReport,
    capabilities=[url_scan_instrumentation()],
)


def _default_weather_model(_settings: Settings | object) -> Any:
    try:
        return build_url_scan_vertex_model(DEFAULT_WEATHER_MODEL)
    except Exception:
        return ModelId.from_pydantic_ai(DEFAULT_WEATHER_MODEL).to_pydantic_ai_model()


async def evaluate_weather(
    inputs: WeatherInputs,
    settings: Settings | object,
    *,
    job_id: UUID,
) -> WeatherReport:
    """Run the weather-report synthesis agent and return a structured WeatherReport."""
    del job_id
    model = _default_weather_model(settings)
    result = await weather_report_agent.run(
        _serialize_inputs(inputs),
        model=model,
        instructions=WEATHER_SYSTEM_PROMPT,
        model_settings=ModelSettings(temperature=0.0),
    )
    return cast(WeatherReport, result.output)


__all__ = [
    "DEFAULT_WEATHER_MODEL",
    "WEATHER_SYSTEM_PROMPT",
    "WeatherInputs",
    "evaluate_weather",
    "weather_report_agent",
]
