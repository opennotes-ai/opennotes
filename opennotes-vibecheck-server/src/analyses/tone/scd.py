"""Speaker Conversational Dynamics (SCD) analysis via the Cornell ConvoKit prompt.

Pure function that takes a list of `Utterance` objects and returns an
`SCDReport`. Uses the shared pydantic-ai Agent factory (`build_agent`) bound
to Vertex AI Gemini. For inputs that are not a real multi-speaker exchange
(fewer than two utterances OR fewer than two distinct authors), no LLM call
is made and a minimal `insufficient_conversation=True` report is returned.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.config import Settings
from src.services.gemini_agent import build_agent
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
    """Load the vendored Cornell ConvoKit SCD prompt once per process."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_utterances(utterances: list[Utterance]) -> str:
    """Render utterances as `author: text` lines joined by newlines.

    Authors are normalized to a stable `Speaker<N>` label when missing so
    downstream prompts never see `None: ...`. This keeps the style close to
    the ConvoKit example ('Speaker1', 'Speaker2', ...).
    """
    lines: list[str] = []
    anon_index = 0
    for utterance in utterances:
        author = utterance.author
        if not author:
            anon_index += 1
            author = f"Speaker{anon_index}"
        lines.append(f"{author}: {utterance.text}")
    return "\n".join(lines)


def _distinct_authors(utterances: list[Utterance]) -> int:
    return len({u.author for u in utterances if u.author})


def _insufficient_report() -> SCDReport:
    return SCDReport(
        summary=_INSUFFICIENT_SUMMARY,
        tone_labels=[],
        per_speaker_notes={},
        insufficient_conversation=True,
    )


async def analyze_scd(
    utterances: list[Utterance],
    settings: Settings,
) -> SCDReport:
    """Analyze tone/dynamics of a conversation using the ConvoKit SCD prompt.

    Args:
        utterances: Ordered list of utterances from `extract_utterances`.
        settings: Application settings (provides Vertex AI project/location/model).

    Returns:
        SCDReport. If the input has fewer than two utterances OR fewer than
        two distinct authors, an `insufficient_conversation=True` report is
        returned without invoking the LLM.
    """
    if len(utterances) < 2 or _distinct_authors(utterances) < 2:
        return _insufficient_report()

    prompt = _load_scd_prompt()
    agent = build_agent(settings, output_type=SCDReport, system_prompt=prompt)
    formatted = _format_utterances(utterances)
    result = await agent.run(formatted)
    return result.output
