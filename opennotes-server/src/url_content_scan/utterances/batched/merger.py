"""Merge per-section UtterancesPayload results into a single de-duplicated payload.

Ported from vibecheck PR603 (TASK-1649). Unlike the vibecheck assembler this
version uses simple whitespace-normalised text equality for deduplication,
not global byte-offset tracking. The deterministic HTML extractor in
opennotes-server does not propagate byte offsets, so offset-based dedup
would give no benefit over text-based dedup.

Deduplication strategy (within the overlap zone):
- Normalise whitespace in utterance text.
- On the second occurrence of the same normalised text, drop it and keep the
  first (from the earlier section).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from src.url_content_scan.utterances.schema import Utterance, UtterancesPayload

_WS_RE = re.compile(r"\s+")


def _norm_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def merge_section_payloads(
    section_payloads: list[UtterancesPayload],
    *,
    source_url: str,
) -> UtterancesPayload:
    """Merge a list of per-section payloads into one, deduplicating overlap.

    Preserves section order and the within-section ordering of utterances.
    Utterances with identical whitespace-normalised text are deduplicated;
    only the first occurrence (from the earliest section) is kept.

    Returns an empty payload when ``section_payloads`` is empty or all
    sections produced zero utterances.
    """
    seen_texts: set[str] = set()
    merged_utterances: list[Utterance] = []

    for payload in section_payloads:
        for utterance in payload.utterances:
            key = _norm_ws(utterance.text)
            if key and key in seen_texts:
                continue
            seen_texts.add(key)
            merged_utterances.append(utterance)

    page_kind = None
    page_title = None
    for payload in section_payloads:
        if payload.page_kind is not None:
            page_kind = payload.page_kind
        if payload.page_title is not None:
            page_title = payload.page_title

    from src.url_content_scan.schemas import PageKind  # noqa: PLC0415

    return UtterancesPayload(
        source_url=source_url,
        scraped_at=datetime.now(UTC),
        utterances=merged_utterances,
        page_title=page_title,
        page_kind=page_kind or PageKind.OTHER,
    )
