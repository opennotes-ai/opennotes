"""Speaker Conversational Dynamics (SCD) analysis.

Pure function that takes a list of `Utterance` objects and returns an
`SCDReport`. Uses the shared pydantic-ai Agent factory (`build_agent`) bound
to Vertex AI Gemini. The prompt (`prompts/scd_prompt.txt`) is an OpenNotes
adaptation of Cornell ConvoKit's SCD prompt, rewritten for conversational
register and to populate the `narrative` + `speaker_arcs` fields on
`SCDReport` alongside the legacy back-compat fields.

For inputs that are not a real multi-speaker exchange (fewer than two
utterances OR fewer than two distinct authors), no LLM call is made and a
minimal `insufficient_conversation=True` report is returned.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.config import Settings
from src.services.gemini_agent import build_agent
from src.services.vertex_limiter import vertex_slot
from src.utterances import Utterance

from ._scd_schemas import SCDReport

__all__ = ["SCDReport", "analyze_scd"]

_PROMPT_PATH = Path(__file__).parent / "prompts" / "scd_prompt.txt"

_INSUFFICIENT_SUMMARY = (
    "Insufficient conversation for dynamics analysis: fewer than two "
    "distinct speakers participated, so no cross-speaker trajectory can "
    "be summarized."
)


@lru_cache(maxsize=1)
def _load_scd_prompt() -> str:
    """Load the SCD prompt (OpenNotes adaptation of ConvoKit's) once per process."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _normalize_utterance_text(text: str) -> str:
    """Collapse internal whitespace to spaces so each utterance is exactly one line.

    The SCD prompt asks the LLM to localize per-speaker arcs by 1-indexed
    `[N]` markers; embedded newlines or tabs in `utterance.text` would split a
    single utterance across multiple lines and break that contract.
    """
    return " ".join(text.split())


def _format_utterances(utterances: list[Utterance]) -> str:
    """Render utterances as `[id] author: text` lines joined by newlines.

    Each line is prefixed with a 1-indexed bracketed id so the prompt can ask
    the LLM to localize per-speaker arcs to a contiguous `utterance_id_range`
    span. Authors are normalized to a stable `Speaker<N>` label when missing
    so downstream prompts never see `None: ...` (this keeps the style close to
    the original ConvoKit example: `Speaker1`, `Speaker2`, ...). Utterance
    text is normalized via `_normalize_utterance_text` so each line is exactly
    one line — this keeps `[N]` span localization reliable.
    """
    lines: list[str] = []
    anon_index = 0
    for idx, utterance in enumerate(utterances, start=1):
        author = utterance.author
        if not author:
            anon_index += 1
            author = f"Speaker{anon_index}"
        lines.append(f"[{idx}] {author}: {_normalize_utterance_text(utterance.text)}")
    return "\n".join(lines)


def _distinct_authors(utterances: list[Utterance]) -> int:
    return len({u.author for u in utterances if u.author})


def _insufficient_report() -> SCDReport:
    return SCDReport(
        narrative="",
        speaker_arcs=[],
        summary=_INSUFFICIENT_SUMMARY,
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=True,
    )


async def analyze_scd(
    utterances: list[Utterance],
    settings: Settings,
) -> SCDReport:
    """Analyze tone/dynamics of a conversation using the SCD prompt.

    Args:
        utterances: Ordered list of utterances from `extract_utterances`.
        settings: Application settings (provides Vertex AI project/location/model).

    Returns:
        SCDReport with `narrative` + `speaker_arcs` populated alongside the
        legacy back-compat fields. If the input has fewer than two utterances
        OR fewer than two distinct authors, an `insufficient_conversation=True`
        report is returned without invoking the LLM.
    """
    if len(utterances) < 2 or _distinct_authors(utterances) < 2:
        return _insufficient_report()

    prompt = _load_scd_prompt()
    agent = build_agent(
        settings,
        output_type=SCDReport,
        system_prompt=prompt,
        name="vibecheck.scd",
    )
    formatted = _format_utterances(utterances)
    async with vertex_slot(settings):
        result = await agent.run(formatted)
    return result.output
