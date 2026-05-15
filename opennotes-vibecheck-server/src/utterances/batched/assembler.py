import re
from dataclasses import dataclass
from datetime import datetime, timezone

from src.utterances.schema import Utterance, UtterancesPayload, BatchedUtteranceRedirectionResponse
from src.utterances.batched.partition import HtmlSection
from src.analyses.schemas import PageKind, UtteranceStreamType


@dataclass(frozen=True)
class SectionResult:
    section: HtmlSection
    payload: UtterancesPayload
    per_section_page_kind_guess: PageKind | None = None


@dataclass
class _Candidate:
    global_offset: int
    length: int
    section_index: int
    local_index: int
    utterance: Utterance
    original_id: str | None


def _norm_ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _find_offset(utterance_text: str, html_slice: str, global_start: int) -> tuple[int, int]:
    match = html_slice.find(utterance_text)
    if match != -1:
        return global_start + match, len(utterance_text)

    norm_utterance = _norm_ws(utterance_text)
    norm_html = _norm_ws(html_slice)
    match = norm_html.find(norm_utterance)
    if match != -1:
        return global_start + match, len(norm_utterance)

    return global_start, 0


def assemble_sections(
    section_results: list[SectionResult],
    parent: BatchedUtteranceRedirectionResponse,
    sanitized_html: str,
    source_url: str,
) -> UtterancesPayload:
    candidates = []

    for result in section_results:
        for local_index, utterance in enumerate(result.payload.utterances):
            global_offset, length = _find_offset(
                utterance.text,
                result.section.html_slice,
                result.section.global_start,
            )
            candidates.append(
                _Candidate(
                    global_offset=global_offset,
                    length=length,
                    section_index=result.section.index,
                    local_index=local_index,
                    utterance=utterance,
                    original_id=utterance.utterance_id,
                )
            )

    candidates.sort(key=lambda c: (c.global_offset, c.section_index, c.local_index))

    emitted = []
    prev_section_index = None
    prev_section_overlap_end = None

    section_by_index = {result.section.index: result.section for result in section_results}

    for i, candidate in enumerate(candidates):
        if candidate.section_index != prev_section_index and prev_section_index is not None:
            if prev_section_index in section_by_index:
                section = section_by_index[prev_section_index]
                prev_section_overlap_end = section.global_end

        is_duplicate = False

        if (
            prev_section_overlap_end is not None
            and candidate.global_offset < prev_section_overlap_end
        ):
            candidate_norm = _norm_ws(candidate.utterance.text)
            for emitted_candidate in emitted:
                if (
                    emitted_candidate.section_index == prev_section_index
                    and emitted_candidate.global_offset < prev_section_overlap_end
                ):
                    emitted_norm = _norm_ws(emitted_candidate.utterance.text)
                    if candidate_norm == emitted_norm:
                        is_duplicate = True
                        break

        if not is_duplicate:
            emitted.append(candidate)

        prev_section_index = candidate.section_index

    utterances = [
        Utterance(
            utterance_id=f"{c.utterance.kind}-{c.section_index}-{c.local_index:04x}",
            kind=c.utterance.kind,
            text=c.utterance.text,
            author=c.utterance.author,
            timestamp=c.utterance.timestamp,
            parent_id=None,
            mentioned_urls=c.utterance.mentioned_urls,
            mentioned_images=c.utterance.mentioned_images,
            mentioned_videos=c.utterance.mentioned_videos,
        )
        for c in emitted
    ]

    page_kind = PageKind.OTHER
    utterance_stream_type = UtteranceStreamType.UNKNOWN
    if section_results:
        page_kind = section_results[0].payload.page_kind
        utterance_stream_type = section_results[0].payload.utterance_stream_type

    return UtterancesPayload(
        source_url=source_url,
        scraped_at=datetime.now(timezone.utc),
        utterances=utterances,
        page_kind=page_kind,
        utterance_stream_type=utterance_stream_type,
    )
