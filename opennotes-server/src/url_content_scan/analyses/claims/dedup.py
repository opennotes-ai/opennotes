from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from src.url_content_scan.claims_schemas import ClaimsReport, DedupedClaim
from src.url_content_scan.utterances.schema import Utterance

DEFAULT_CLAIMS_SIMILARITY_THRESHOLD = 0.85
DEFAULT_CLAIMS_CONCURRENCY = 8


class ExtractedClaim(BaseModel):
    claim_text: str
    confidence: float = Field(ge=0.0, le=1.0)


ClaimExtractor = Callable[[Utterance], Awaitable[list[ExtractedClaim]]]
TextEmbedder = Callable[[list[str]], Awaitable[list[list[float]]]]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right, strict=True):
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value

    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0

    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, index: int) -> int:
        root = index
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[index] != root:
            self._parent[index], index = root, self._parent[index]
        return root

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root


def _empty_report() -> ClaimsReport:
    return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)


async def _extract_claim_batches(
    utterances: list[Utterance],
    *,
    extract_claims: ClaimExtractor,
    max_concurrency: int,
) -> list[list[ExtractedClaim]]:
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[list[ExtractedClaim]] = [[] for _utterance in utterances]

    async def _extract_one(index: int, utterance: Utterance) -> None:
        if not utterance.text.strip():
            return
        async with semaphore:
            results[index] = await extract_claims(utterance)

    async with asyncio.TaskGroup() as task_group:
        for index, utterance in enumerate(utterances):
            task_group.create_task(_extract_one(index, utterance))
    return results


def _flatten_claims(
    utterances: list[Utterance],
    per_utterance_claims: list[list[ExtractedClaim]],
) -> tuple[list[tuple[ExtractedClaim, str]], dict[str, str | None]]:
    flattened: list[tuple[ExtractedClaim, str]] = []
    author_by_utterance: dict[str, str | None] = {}
    for index, utterance in enumerate(utterances):
        utterance_id = utterance.utterance_id or f"utt-{index}"
        author_by_utterance[utterance_id] = utterance.author
        flattened.extend(
            (claim, utterance_id)
            for claim in per_utterance_claims[index]
            if claim.claim_text.strip()
        )
    return flattened, author_by_utterance


def _cluster_claims(
    flattened: list[tuple[ExtractedClaim, str]],
    embeddings: list[list[float]],
    *,
    similarity_threshold: float,
) -> dict[int, list[int]]:
    union_find = _UnionFind(len(flattened))
    for left_index in range(len(flattened)):
        for right_index in range(left_index + 1, len(flattened)):
            similarity = _cosine_similarity(embeddings[left_index], embeddings[right_index])
            if similarity >= similarity_threshold:
                union_find.union(left_index, right_index)

    clusters: dict[int, list[int]] = {}
    for claim_index in range(len(flattened)):
        clusters.setdefault(union_find.find(claim_index), []).append(claim_index)
    return clusters


def _to_deduped_claim(
    members: list[tuple[ExtractedClaim, str]],
    author_by_utterance: dict[str, str | None],
) -> DedupedClaim:
    canonical_claim, _canonical_utterance_id = max(
        members,
        key=lambda member: member[0].confidence,
    )
    utterance_ids = [utterance_id for _claim, utterance_id in members]
    representative_authors: list[str] = []
    seen_authors: set[str] = set()
    for utterance_id in utterance_ids:
        author = author_by_utterance.get(utterance_id)
        if author and author not in seen_authors:
            seen_authors.add(author)
            representative_authors.append(author)

    return DedupedClaim(
        canonical_text=canonical_claim.claim_text,
        occurrence_count=len(members),
        author_count=len(seen_authors),
        utterance_ids=utterance_ids,
        representative_authors=representative_authors[:5],
    )


async def run_claims_dedup(
    utterances: list[Utterance],
    *,
    extract_claims: ClaimExtractor,
    embed_texts: TextEmbedder,
    similarity_threshold: float = DEFAULT_CLAIMS_SIMILARITY_THRESHOLD,
    max_concurrency: int = DEFAULT_CLAIMS_CONCURRENCY,
) -> ClaimsReport:
    """Extract claims per utterance, then semantically cluster them.

    External LM and embedding work stays injectable so TASK-1487.13 can wire
    concrete services later without widening this slice.
    """
    if not utterances:
        return _empty_report()

    per_utterance_claims = await _extract_claim_batches(
        utterances,
        extract_claims=extract_claims,
        max_concurrency=max_concurrency,
    )
    flattened, author_by_utterance = _flatten_claims(utterances, per_utterance_claims)

    if not flattened:
        return _empty_report()

    claim_texts = [claim.claim_text for claim, _utterance_id in flattened]
    embeddings = await embed_texts(claim_texts)
    if len(embeddings) != len(flattened):
        raise RuntimeError(
            f"embed_texts returned {len(embeddings)} embeddings for {len(flattened)} claims"
        )

    clusters = _cluster_claims(
        flattened,
        embeddings,
        similarity_threshold=similarity_threshold,
    )

    deduped_claims: list[DedupedClaim] = []
    for member_indices in clusters.values():
        members = [flattened[member_index] for member_index in member_indices]
        deduped_claims.append(_to_deduped_claim(members, author_by_utterance))

    deduped_claims.sort(key=lambda claim: claim.occurrence_count, reverse=True)
    return ClaimsReport(
        deduped_claims=deduped_claims,
        total_claims=len(flattened),
        total_unique=len(deduped_claims),
    )


__all__ = [
    "DEFAULT_CLAIMS_CONCURRENCY",
    "DEFAULT_CLAIMS_SIMILARITY_THRESHOLD",
    "ClaimExtractor",
    "ExtractedClaim",
    "TextEmbedder",
    "run_claims_dedup",
]
