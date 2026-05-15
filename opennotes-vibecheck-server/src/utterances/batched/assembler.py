import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from src.utterances.schema import Utterance, UtterancesPayload, BatchedUtteranceRedirectionResponse
from src.utterances.batched.partition import HtmlSection
from src.utterances._ids import stable_utterance_id, _norm_ws
from src.utterances.media_extraction import attribute_media
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


def _is_split_token_artifact(prior_last_text: str, candidate_text: str) -> bool:
    prior_words = prior_last_text.split()
    if not prior_words:
        return False
    last_word = prior_words[-1]
    for split_point in range(1, len(last_word) - 2):
        suffix = last_word[split_point:]
        if len(suffix) >= 3 and candidate_text.startswith(suffix):
            return True
    return False


def _find_offset(utterance_text: str, html_slice: str, global_start: int) -> tuple[int, int]:
    match = html_slice.find(utterance_text)
    if match != -1:
        return global_start + match, len(utterance_text)

    norm_utterance = _norm_ws(utterance_text)
    norm_html = _norm_ws(html_slice)
    match = norm_html.find(norm_utterance)
    if match != -1:
        return global_start, len(utterance_text)

    return global_start, 0


async def assemble_sections(
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
    prior_section_last_emitted_text: str | None = None

    section_by_index = {result.section.index: result.section for result in section_results}

    for i, candidate in enumerate(candidates):
        if candidate.section_index != prev_section_index and prev_section_index is not None:
            if prev_section_index in section_by_index:
                section = section_by_index[prev_section_index]
                prev_section_overlap_end = section.global_end
            prior_section_last_emitted_text = (
                next(
                    (e.utterance.text for e in reversed(emitted) if e.section_index == prev_section_index),
                    None,
                )
            )

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

            if not is_duplicate and prior_section_last_emitted_text is not None:
                if _is_split_token_artifact(prior_section_last_emitted_text, candidate.utterance.text):
                    is_duplicate = True

        if not is_duplicate:
            emitted.append(candidate)

        prev_section_index = candidate.section_index

    survivors = emitted

    for ordinal, candidate in enumerate(survivors):
        candidate.utterance.utterance_id = stable_utterance_id(
            candidate.utterance.kind,
            candidate.utterance.text,
            candidate.global_offset,
            ordinal,
        )

    local_to_final: dict[str, str] = {}
    for candidate in sorted(survivors, key=lambda c: c.section_index):
        if candidate.original_id is not None:
            local_to_final[candidate.original_id] = candidate.utterance.utterance_id

    surviving_utterances = [c.utterance for c in survivors]

    for i, candidate in enumerate(survivors):
        utt = candidate.utterance
        if utt.parent_id is None:
            continue
        resolved = local_to_final.get(utt.parent_id)
        if resolved is not None:
            utt.parent_id = resolved
        else:
            preceding_post: str | None = None
            for j in range(i - 1, -1, -1):
                if surviving_utterances[j].kind == "post":
                    preceding_post = surviving_utterances[j].utterance_id
                    break
            utt.parent_id = preceding_post

    utterances = [
        Utterance(
            utterance_id=c.utterance.utterance_id,
            kind=c.utterance.kind,
            text=c.utterance.text,
            author=c.utterance.author,
            timestamp=c.utterance.timestamp,
            parent_id=c.utterance.parent_id,
            mentioned_urls=c.utterance.mentioned_urls,
            mentioned_images=c.utterance.mentioned_images,
            mentioned_videos=c.utterance.mentioned_videos,
        )
        for c in survivors
    ]

    payload = UtterancesPayload(
        source_url=source_url,
        scraped_at=datetime.now(timezone.utc),
        utterances=utterances,
        page_title=parent.page_title,
        page_kind=parent.page_kind,
        utterance_stream_type=parent.utterance_stream_type,
    )

    await asyncio.to_thread(attribute_media, sanitized_html, payload.utterances)

    return payload
