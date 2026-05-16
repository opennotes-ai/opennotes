"""Pure tone-analysis helpers for URL content scan.

This package computes tone outputs only. Slot persistence and DBOS wiring are
handled separately by TASK-1487.13.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

from src.bulk_content_scan.flashpoint_service import (
    FlashpointDetectionService,
    get_flashpoint_service,
)
from src.url_content_scan.schemas import PageKind
from src.url_content_scan.tone_schemas import FlashpointMatch, SCDReport, SpeakerArc
from src.url_content_scan.utterances.schema import Utterance

_MAX_FLASHPOINT_CONCURRENCY = 8
_DEFAULT_LINEAR_CONTEXT = FlashpointDetectionService.DEFAULT_MAX_CONTEXT
_WORD_RE = re.compile(r"\w+")


def _normalized_text(text: str) -> str:
    words = _WORD_RE.findall(text.lower())
    return " ".join(words)


def _speaker_label(utterance: Utterance, fallback_index: int) -> str:
    return utterance.author or utterance.utterance_id or f"speaker_{fallback_index}"


def _build_parent_chain_context(
    utterance: Utterance,
    by_id: dict[str, Utterance],
) -> list[Utterance]:
    context: list[Utterance] = []
    seen: set[str] = set()
    parent_id = utterance.parent_id
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id.get(parent_id)
        if parent is None:
            break
        context.append(parent)
        parent_id = parent.parent_id
    context.reverse()
    return context


def _build_flashpoint_contexts(
    utterances: list[Utterance],
    max_linear_context: int,
    *,
    page_kind: PageKind,
) -> dict[str, list[Utterance]]:
    by_id = {
        utterance.utterance_id: utterance for utterance in utterances if utterance.utterance_id
    }
    contexts: dict[str, list[Utterance]] = {}

    for index, utterance in enumerate(utterances):
        utterance_id = utterance.utterance_id
        if utterance_id is None:
            continue
        if page_kind == PageKind.HIERARCHICAL_THREAD and utterance.parent_id:
            contexts[utterance_id] = _build_parent_chain_context(utterance, by_id)
            continue
        start_index = max(0, index - max_linear_context)
        contexts[utterance_id] = utterances[start_index:index]

    return contexts


async def run_flashpoint(
    utterances: list[Utterance],
    *,
    service: FlashpointDetectionService | None = None,
    max_context: int | None = None,
    score_threshold: int | None = None,
    max_concurrency: int = _MAX_FLASHPOINT_CONCURRENCY,
    page_kind: PageKind = PageKind.OTHER,
) -> list[FlashpointMatch]:
    """Analyze utterances for flashpoint risk using the shared service."""
    if not utterances:
        return []

    flashpoint_service = service or get_flashpoint_service()
    linear_context = max_context or _DEFAULT_LINEAR_CONTEXT
    contexts = _build_flashpoint_contexts(
        utterances,
        max_linear_context=linear_context,
        page_kind=page_kind,
    )
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[FlashpointMatch | None] = [None] * len(utterances)

    async def _detect(index: int, utterance: Utterance) -> None:
        if utterance.utterance_id is None:
            return
        async with semaphore:
            results[index] = await flashpoint_service.detect_flashpoint_for_utterance(
                utterance,
                contexts.get(utterance.utterance_id, []),
                max_context=max_context,
                score_threshold=score_threshold,
            )

    await asyncio.gather(*(_detect(index, utterance) for index, utterance in enumerate(utterances)))
    return [result for result in results if result is not None]


@dataclass(frozen=True)
class _ConversationStats:
    speaker_count: int
    transition_ratio: float
    turn_entropy: float
    repetition_ratio: float
    timing_coverage: float
    average_latency_seconds: float


def _compute_conversation_stats(utterances: list[Utterance]) -> _ConversationStats:
    if not utterances:
        return _ConversationStats(
            speaker_count=0,
            transition_ratio=0.0,
            turn_entropy=0.0,
            repetition_ratio=0.0,
            timing_coverage=0.0,
            average_latency_seconds=0.0,
        )

    speakers = [_speaker_label(utterance, index + 1) for index, utterance in enumerate(utterances)]
    counts = Counter(speakers)
    total_turns = len(utterances)
    speaker_count = len(counts)

    transitions = sum(1 for previous, current in pairwise(speakers) if previous != current)
    transition_ratio = transitions / (total_turns - 1) if total_turns > 1 else 0.0

    probabilities = [count / total_turns for count in counts.values()]
    entropy = -sum(
        probability * math.log2(probability) for probability in probabilities if probability
    )
    normalized_entropy = entropy / math.log2(speaker_count) if speaker_count > 1 else 0.0

    normalized_texts = [_normalized_text(utterance.text) for utterance in utterances]
    duplicate_turns = sum(
        count - 1 for text, count in Counter(normalized_texts).items() if text and count > 1
    )
    repetition_ratio = duplicate_turns / total_turns if total_turns else 0.0

    timed_turns = sum(1 for utterance in utterances if utterance.timestamp is not None)
    timing_coverage = timed_turns / total_turns if total_turns else 0.0
    latencies = [
        (current.timestamp - previous.timestamp).total_seconds()
        for previous, current in pairwise(utterances)
        if previous.timestamp is not None
        and current.timestamp is not None
        and current.timestamp >= previous.timestamp
    ]
    average_latency_seconds = sum(latencies) / len(latencies) if latencies else 0.0

    return _ConversationStats(
        speaker_count=speaker_count,
        transition_ratio=transition_ratio,
        turn_entropy=normalized_entropy,
        repetition_ratio=repetition_ratio,
        timing_coverage=timing_coverage,
        average_latency_seconds=average_latency_seconds,
    )


def _tone_labels(stats: _ConversationStats, speaker_shares: dict[str, float]) -> list[str]:
    labels: list[str] = []
    labels.append("multi_speaker" if stats.speaker_count > 1 else "single_speaker")
    if stats.turn_entropy >= 0.8 and stats.speaker_count > 1:
        labels.append("balanced_participation")
    if stats.transition_ratio >= 0.75:
        labels.append("rapid_turn_taking")
    if stats.repetition_ratio > 0.0:
        labels.append("repetitive")
    dominant_speaker = max(speaker_shares.items(), key=lambda item: item[1], default=None)
    if dominant_speaker and dominant_speaker[1] >= 0.6:
        labels.append(f"dominated_by_{dominant_speaker[0]}")
    return labels


async def run_scd(utterances: list[Utterance]) -> SCDReport:
    """Compute statistical conversation-dynamics output without using an LM."""
    if not utterances:
        return SCDReport(
            narrative="No conversation was available for tone-dynamics analysis.",
            speaker_arcs=[],
            summary=(
                "speaker_count=0 total_turns=0 turn_entropy=0.00 "
                "transition_ratio=0.00 repeat_ratio=0.00 timing_coverage=0.00"
            ),
            tone_labels=["insufficient_conversation"],
            per_speaker_notes={},
            insufficient_conversation=True,
        )

    stats = _compute_conversation_stats(utterances)
    speakers = [_speaker_label(utterance, index + 1) for index, utterance in enumerate(utterances)]
    counts = Counter(speakers)
    total_turns = len(utterances)
    speaker_shares = {speaker: count / total_turns for speaker, count in counts.items()}
    labels = _tone_labels(stats, speaker_shares)

    per_speaker_notes: dict[str, str] = {}
    speaker_arcs: list[SpeakerArc] = []
    for speaker in counts:
        indices = [index + 1 for index, label in enumerate(speakers) if label == speaker]
        share = speaker_shares[speaker]
        note = (
            f"{speaker} takes {len(indices)}/{total_turns} turns "
            f"({share:.0%}) across turns {indices[0]}-{indices[-1]}."
        )
        per_speaker_notes[speaker] = note
        speaker_arcs.append(
            SpeakerArc(
                speaker=speaker,
                note=note,
                utterance_id_range=[indices[0], indices[-1]],
            )
        )

    insufficient = total_turns < 2 or stats.speaker_count < 2
    if insufficient and "insufficient_conversation" not in labels:
        labels.append("insufficient_conversation")

    narrative = (
        f"The thread spans {total_turns} turns across {stats.speaker_count} speakers. "
        f"Turn-taking entropy is {stats.turn_entropy:.2f} and speaker transitions land at "
        f"{stats.transition_ratio:.2f}, with repetition at {stats.repetition_ratio:.2f} "
        f"and average reply latency at {stats.average_latency_seconds:.0f} seconds."
    )
    summary = (
        f"speaker_count={stats.speaker_count} total_turns={total_turns} "
        f"turn_entropy={stats.turn_entropy:.2f} transition_ratio={stats.transition_ratio:.2f} "
        f"repeat_ratio={stats.repetition_ratio:.2f} timing_coverage={stats.timing_coverage:.2f} "
        f"avg_latency_seconds={stats.average_latency_seconds:.0f}"
    )

    return SCDReport(
        narrative=narrative,
        speaker_arcs=speaker_arcs,
        summary=summary,
        tone_labels=labels,
        per_speaker_notes=per_speaker_notes,
        insufficient_conversation=insufficient,
    )


__all__ = ["run_flashpoint", "run_scd"]
