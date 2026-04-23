"""TASK-1471.23.08 — SCD conversational-register before/after eval.

One-off script. Runs `analyze_scd` against three hand-crafted transcripts using
both the OLD prompt (Cornell ConvoKit verbatim, recovered from parent commit
90e2185d) and the NEW prompt (current `scd_prompt.txt` on this branch). Dumps
each before/after SCDReport JSON to disk so the eval markdown can compare them
side-by-side.

The OLD prompt embeds a `{formatted_object}` placeholder; we interpolate the
formatted transcript into the system prompt and send a minimal cue as the user
message ("Produce the trajectory summary as instructed above.") so the call is
well-formed for Vertex Gemini, which rejects empty input. The NEW prompt is a
pure system prompt and receives the formatted transcript as the user message
(matching production wiring in `analyze_scd`).

Usage (from `opennotes-vibecheck-server/`):

    uv run python scripts/eval_scd_register.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.analyses.tone._scd_schemas import SCDReport
from src.analyses.tone.scd import (
    _distinct_authors,
    _format_utterances,
    _insufficient_report,
)
from src.config import Settings
from src.services.gemini_agent import build_agent
from src.utterances import Utterance

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "docs" / "specs" / "vibecheck" / "scd-register-eval"
NEW_PROMPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "analyses"
    / "tone"
    / "prompts"
    / "scd_prompt.txt"
)
OLD_PROMPT_PATH = EVAL_DIR / "_old_prompt.txt"


TRANSCRIPT_1_HEATED: list[Utterance] = [
    Utterance(
        kind="post",
        author="op_throwaway",
        text=(
            "My partner of 4 years just told me they don't want kids anymore. "
            "We agreed on having a family before we got engaged. I feel like "
            "the rug got pulled out and I don't know if this is something we "
            "can come back from. Am I overreacting?"
        ),
    ),
    Utterance(
        kind="comment",
        author="alex_91",
        text=(
            "You're not overreacting. This is a fundamental life thing. "
            "People are allowed to change their minds but you're also "
            "allowed to leave over it."
        ),
    ),
    Utterance(
        kind="comment",
        author="brenna_h",
        text=(
            "Counterpoint: have you actually sat down and asked WHY they "
            "changed their mind? Could be fear, could be money, could be "
            "trauma surfacing. 'They changed their mind' isn't the same as "
            "'they lied to me'."
        ),
    ),
    Utterance(
        kind="comment",
        author="alex_91",
        text=(
            "@brenna_h with respect, that's a lot of free labor you're "
            "asking OP to do. Their partner moved the goalposts. The burden "
            "of explaining is on the person who shifted, not on OP to "
            "interrogate them into a justification."
        ),
    ),
    Utterance(
        kind="comment",
        author="brenna_h",
        text=(
            "I'm not asking OP to do anything. I'm asking them to be curious "
            "before they nuke a 4-year relationship over one conversation. "
            "There's a difference between accountability and curiosity."
        ),
    ),
    Utterance(
        kind="comment",
        author="op_throwaway",
        text=(
            "We did talk. They said they've been thinking about it for "
            "months, watching friends with kids, and they don't think they "
            "have it in them. It wasn't a flip thing. That's almost worse "
            "honestly because it means they sat on it."
        ),
    ),
    Utterance(
        kind="comment",
        author="cyrus_t",
        text=(
            "Both of you are right and both of you are missing the point. "
            "OP isn't asking permission to leave. OP is grieving in real "
            "time and looking for someone to tell them their feelings are "
            "real. Yes they are. Take a beat before you decide anything."
        ),
    ),
    Utterance(
        kind="comment",
        author="alex_91",
        text=(
            "@cyrus_t okay that one I'll concede. Reading it back I came in "
            "hotter than I needed to. OP, sorry — Cyrus is right, you don't "
            "owe anyone a decision today."
        ),
    ),
    Utterance(
        kind="comment",
        author="brenna_h",
        text=(
            "Same here. OP, whatever you decide, decide it on your own "
            "timeline. I'm sorry this is happening."
        ),
    ),
]


TRANSCRIPT_2_MEASURED: list[Utterance] = [
    Utterance(
        kind="post",
        author="dgreene",
        text=(
            "Genuine question for the framework people: at what team size "
            "does the maintenance cost of a custom in-house framework start "
            "to exceed the cost of just adopting Next.js or Remix and "
            "absorbing the lock-in?"
        ),
    ),
    Utterance(
        kind="comment",
        author="emoss",
        text=(
            "In my experience the inflection point is around 8-10 product "
            "engineers. Below that you can't justify a dedicated platform "
            "team, and the framework rots. Above that the lock-in starts to "
            "bite back in customization velocity."
        ),
    ),
    Utterance(
        kind="comment",
        author="fperez",
        text=(
            "I'd push back gently — team size is a proxy. What actually "
            "matters is how much of your routing/data/auth shape is unusual "
            "enough that an off-the-shelf framework forces you into "
            "constant escape hatches."
        ),
    ),
    Utterance(
        kind="comment",
        author="emoss",
        text=(
            "Fair. Team size correlates because larger teams tend to have "
            "the unusual shape that justifies the custom work. But you're "
            "right that the underlying variable is shape-fit, not "
            "headcount."
        ),
    ),
    Utterance(
        kind="comment",
        author="dgreene",
        text=(
            "Both framings are useful. I think the practical heuristic is: "
            "if you're writing more than ~20% of your week working around "
            "the framework rather than with it, that's the signal — "
            "regardless of team size."
        ),
    ),
    Utterance(
        kind="comment",
        author="fperez",
        text=(
            "That's a clean heuristic. The 20% number maps roughly to the "
            "point where escape hatches stop being exceptions and start "
            "being the default path."
        ),
    ),
]


TRANSCRIPT_3_MONOLOGUE: list[Utterance] = [
    Utterance(
        kind="post",
        author="m_solo",
        text=(
            "I've been writing this newsletter for three years now and the "
            "thing nobody warned me about is that consistency is the entire "
            "game. Not quality, not insight, not luck. Consistency. I "
            "watched a hundred sharper writers than me start strong, run "
            "out of runway around month four, and quietly disappear. "
            "Meanwhile here I am, still writing the same workmanlike "
            "essays, and somehow that turned into an audience."
            "\n\n"
            "The lesson I keep coming back to is that showing up on a "
            "boring Tuesday with something honest beats showing up "
            "occasionally with something brilliant. The compounding only "
            "happens if the compounding gets to happen. There's no shortcut "
            "and there's no substitute, and most of the people who tell "
            "you otherwise are selling something."
        ),
    ),
]


def _format_with_old_prompt(formatted: str, old_prompt: str) -> str:
    """Interpolate `{formatted_object}` like the original ConvoKit prompt."""
    if "{formatted_object}" not in old_prompt:
        raise RuntimeError(
            "Recovered OLD prompt does not contain {formatted_object} placeholder"
        )
    return old_prompt.replace("{formatted_object}", formatted)


async def _run_with_prompt(
    prompt_text: str,
    formatted_utterances: str,
    settings: Settings,
    *,
    interpolate: bool,
) -> SCDReport:
    """Run the LLM with a given prompt template against a formatted transcript.

    When `interpolate=True` (OLD prompt path), the formatted conversation is
    spliced into `{formatted_object}` and an empty user message is sent —
    matching how the ConvoKit-style prompt was originally structured. When
    `interpolate=False` (NEW prompt path), the prompt is used as-is as a system
    prompt and the formatted conversation is sent as the user message —
    matching production wiring in `analyze_scd`.
    """
    if interpolate:
        system_prompt = _format_with_old_prompt(formatted_utterances, prompt_text)
        # Vertex Gemini rejects empty user input; the OLD ConvoKit prompt embeds
        # the conversation in the system prompt and ends with "Trajectory
        # Summary:" expecting the model to continue. We send a minimal cue as
        # the user message so the call is well-formed.
        user_message = "Produce the trajectory summary as instructed above."
    else:
        system_prompt = prompt_text
        user_message = formatted_utterances
    agent = build_agent(settings, output_type=SCDReport, system_prompt=system_prompt)
    result = await agent.run(user_message)
    return result.output


async def _run_with_retry(
    prompt_text: str,
    formatted: str,
    settings: Settings,
    *,
    interpolate: bool,
    label: str,
    max_attempts: int = 3,
) -> SCDReport | dict[str, str]:
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await _run_with_prompt(
                prompt_text, formatted, settings, interpolate=interpolate
            )
        except Exception as exc:
            last_err = exc
            print(f"  [{label}] attempt {attempt} failed: {exc!r}")
    return {"_eval_error": f"{type(last_err).__name__}: {last_err}"}


async def _eval_transcript(
    name: str,
    utterances: list[Utterance],
    new_prompt: str,
    old_prompt: str,
    settings: Settings,
) -> None:
    out_dir = EVAL_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    if len(utterances) < 2 or _distinct_authors(utterances) < 2:
        report = _insufficient_report()
        payload = json.loads(report.model_dump_json())
        payload["_eval_note"] = (
            "insufficient_conversation short-circuit fired before LLM call; "
            "OLD and NEW prompts produce identical output for this input."
        )
        (out_dir / "old.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        (out_dir / "new.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
        print(f"[{name}] short-circuit (insufficient conversation)")
        return

    formatted = _format_utterances(utterances)
    old_path = out_dir / "old.json"
    new_path = out_dir / "new.json"

    def _is_present_and_valid(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return "_eval_error" not in data

    if _is_present_and_valid(old_path):
        print(f"[{name}] OLD already present, skipping LLM call")
    else:
        print(f"[{name}] OLD prompt LLM call...")
        old_result = await _run_with_retry(
            old_prompt, formatted, settings, interpolate=True, label=f"{name}-old"
        )
        if isinstance(old_result, SCDReport):
            old_path.write_text(
                old_result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        else:
            old_path.write_text(
                json.dumps(old_result, indent=2) + "\n", encoding="utf-8"
            )

    if _is_present_and_valid(new_path):
        print(f"[{name}] NEW already present, skipping LLM call")
    else:
        print(f"[{name}] NEW prompt LLM call...")
        new_result = await _run_with_retry(
            new_prompt, formatted, settings, interpolate=False, label=f"{name}-new"
        )
        if isinstance(new_result, SCDReport):
            new_path.write_text(
                new_result.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        else:
            new_path.write_text(
                json.dumps(new_result, indent=2) + "\n", encoding="utf-8"
            )

    print(f"[{name}] done")


def _write_transcripts_md() -> None:
    parts: list[str] = ["# Transcripts (TASK-1471.23.08 SCD eval)\n"]
    for name, transcript in [
        ("transcript-1-heated", TRANSCRIPT_1_HEATED),
        ("transcript-2-measured", TRANSCRIPT_2_MEASURED),
        ("transcript-3-monologue", TRANSCRIPT_3_MONOLOGUE),
    ]:
        parts.append(f"\n## {name}\n")
        for idx, utt in enumerate(transcript, start=1):
            author = utt.author or f"Speaker{idx}"
            parts.append(f"\n**[{idx}] {author}** ({utt.kind}):  \n{utt.text}\n")
    (EVAL_DIR / "transcripts.md").write_text("".join(parts), encoding="utf-8")


async def main() -> None:
    settings = Settings()
    new_prompt = NEW_PROMPT_PATH.read_text(encoding="utf-8")
    old_prompt = OLD_PROMPT_PATH.read_text(encoding="utf-8")

    _write_transcripts_md()

    transcripts = [
        ("transcript-1-heated", TRANSCRIPT_1_HEATED),
        ("transcript-2-measured", TRANSCRIPT_2_MEASURED),
        ("transcript-3-monologue", TRANSCRIPT_3_MONOLOGUE),
    ]
    for name, utts in transcripts:
        await _eval_transcript(name, utts, new_prompt, old_prompt, settings)

    print("\nAll runs complete. Outputs in:", EVAL_DIR)


if __name__ == "__main__":
    asyncio.run(main())
