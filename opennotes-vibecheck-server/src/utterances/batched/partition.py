from __future__ import annotations

from dataclasses import dataclass

from src.config import Settings
from src.utterances.schema import BatchedUtteranceRedirectionResponse, SectionHint


@dataclass(frozen=True)
class HtmlSection:
    index: int
    html_slice: str
    global_start: int
    global_end: int
    overlap_with_prev_bytes: int
    parent_context_text: str | None


def _snap_to_utf8_boundary(raw: bytes, pos: int) -> int:
    while pos < len(raw) and (raw[pos] & 0xC0) == 0x80:
        pos += 1
    return pos


def _snap_backward_to_utf8_boundary(raw: bytes, pos: int) -> int:
    while pos > 0 and (raw[pos] & 0xC0) == 0x80:
        pos -= 1
    return pos


def partition_html(
    sanitized_html: str,
    response: BatchedUtteranceRedirectionResponse,
    settings: Settings,
) -> list[HtmlSection]:
    raw: bytes = sanitized_html.encode("utf-8")
    total: int = len(raw)

    if total == 0:
        return []

    target_size = settings.VIBECHECK_BATCH_SECTION_TARGET_BYTES
    cuts: list[int] = []
    pos = 0
    while pos < total:
        cuts.append(pos)
        pos += target_size

    if not cuts or cuts[0] != 0:
        cuts.insert(0, 0)

    cuts = sorted(set(cuts))
    cuts = [c for c in cuts if c < total]

    overlap_bytes = settings.VIBECHECK_BATCH_OVERLAP_BYTES

    matched_hints: dict[int, SectionHint | None] = {}
    for cut in cuts:
        matched_hints[cut] = None

    for cut_idx, cut in enumerate(cuts[1:], start=1):
        for hint in response.section_hints:
            tolerance = (
                hint.tolerance_bytes
                if hint.tolerance_bytes is not None
                else target_size // 4
            )
            window_start = max(0, cut - tolerance)
            window_end = min(total, cut + tolerance)

            needle = hint.anchor_hint.encode("utf-8")
            match_pos = raw.find(needle, window_start, window_end)

            if match_pos != -1:
                cuts[cut_idx] = match_pos
                matched_hints[match_pos] = hint
                if cut in matched_hints and matched_hints[cut] is None:
                    del matched_hints[cut]
                break

    for i in range(1, len(cuts)):
        cuts[i] = _snap_to_utf8_boundary(raw, cuts[i])

    filtered_cuts: list[int] = [cuts[0]]
    for i in range(1, len(cuts)):
        if cuts[i] - filtered_cuts[-1] > overlap_bytes:
            filtered_cuts.append(cuts[i])

    cuts = filtered_cuts

    section_starts = cuts
    section_ends = section_starts[1:] + [total]

    sections: list[HtmlSection] = []

    for i, (start, end) in enumerate(zip(section_starts, section_ends)):
        overlap_bytes_for_section = overlap_bytes
        if i > 0:
            matched_hint = matched_hints.get(start)
            if (
                matched_hint
                and matched_hint.overlap_with_prev_bytes is not None
            ):
                overlap_bytes_for_section = max(
                    overlap_bytes, matched_hint.overlap_with_prev_bytes
                )

        global_start = max(0, start - overlap_bytes_for_section) if i > 0 else start
        global_start = _snap_backward_to_utf8_boundary(raw, global_start)

        global_end = end

        html_slice = raw[global_start:global_end].decode("utf-8")

        matched_hint = matched_hints.get(start)
        parent_context_text = (
            matched_hint.parent_context_text if matched_hint else None
        )

        overlap_recorded = start - global_start if i > 0 else 0

        section = HtmlSection(
            index=i,
            html_slice=html_slice,
            global_start=global_start,
            global_end=global_end,
            overlap_with_prev_bytes=overlap_recorded,
            parent_context_text=parent_context_text,
        )
        sections.append(section)

    return sections
