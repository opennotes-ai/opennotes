"""HTML partitioner for batched utterance extraction.

Ported from vibecheck PR603 (TASK-1649). Splits oversized HTML into
overlapping byte-aligned sections. The overlap lets the per-section
extractor capture utterances that straddle a boundary without duplicating
most content.

Unlike the vibecheck version there are no LLM section-hint adjustments —
cuts are placed purely on target byte boundaries and snapped to valid
UTF-8 code-point boundaries. The caller caps the number of sections
via ``max_batches``; when the raw cut count exceeds that cap the
sections are merged by combining contiguous oversized chunks so the
full document is still covered.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HtmlSection:
    index: int
    html_slice: str
    global_start: int
    global_end: int
    overlap_with_prev_bytes: int


def _snap_to_utf8_boundary(raw: bytes, pos: int) -> int:
    while pos < len(raw) and (raw[pos] & 0xC0) == 0x80:
        pos += 1
    return pos


def _snap_backward_to_utf8_boundary(raw: bytes, pos: int) -> int:
    while pos > 0 and (raw[pos] & 0xC0) == 0x80:
        pos -= 1
    return pos


def partition_html(
    html: str,
    *,
    target_bytes: int,
    overlap_bytes: int,
    max_batches: int,
) -> list[HtmlSection]:
    """Partition ``html`` into at most ``max_batches`` overlapping byte sections.

    Returns an empty list for empty input. Returns a single section when
    the entire content fits within ``target_bytes``.

    Each section beyond the first carries ``overlap_with_prev_bytes`` bytes
    of repeated content from the end of the prior section so the extractor
    can see context across boundaries.
    """
    raw: bytes = html.encode("utf-8")
    total: int = len(raw)

    if total == 0:
        return []

    if total <= target_bytes:
        return [
            HtmlSection(
                index=0,
                html_slice=html,
                global_start=0,
                global_end=total,
                overlap_with_prev_bytes=0,
            )
        ]

    cuts: list[int] = []
    pos = 0
    while pos < total:
        cuts.append(pos)
        pos += target_bytes

    if not cuts or cuts[0] != 0:
        cuts.insert(0, 0)

    cuts = sorted(set(cuts))
    cuts = [c for c in cuts if c < total]

    for i in range(1, len(cuts)):
        old_pos = cuts[i]
        new_pos = _snap_to_utf8_boundary(raw, old_pos)
        cuts[i] = new_pos

    filtered_cuts: list[int] = [cuts[0]]
    for i in range(1, len(cuts)):
        if cuts[i] - filtered_cuts[-1] > overlap_bytes:
            filtered_cuts.append(cuts[i])
    cuts = filtered_cuts

    if len(cuts) > max_batches:
        cuts = cuts[:max_batches]

    section_starts = cuts
    section_ends = [*section_starts[1:], total]

    sections: list[HtmlSection] = []
    for i, (start, end) in enumerate(zip(section_starts, section_ends, strict=True)):
        if i == 0:
            global_start = start
            overlap_recorded = 0
        else:
            back = _snap_backward_to_utf8_boundary(raw, max(0, start - overlap_bytes))
            global_start = back
            overlap_recorded = start - global_start

        html_slice = raw[global_start:end].decode("utf-8")
        sections.append(
            HtmlSection(
                index=i,
                html_slice=html_slice,
                global_start=global_start,
                global_end=end,
                overlap_with_prev_bytes=overlap_recorded,
            )
        )

    return sections
