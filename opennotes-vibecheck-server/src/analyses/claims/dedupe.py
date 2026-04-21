"""Semantic dedup + prevalence stats for extracted claims.

Given a flat list of `Claim`s (from all utterances on the page), embed each
claim's text with the shared Vertex `gemini-embedding-001` embedder, cluster by
cosine similarity (single-link, union-find), and return a `ClaimsReport` with
one `DedupedClaim` per cluster. Designed as a pure function so it can be
lifted back into opennotes-server later.
"""
from __future__ import annotations

import math

from src.analyses.claims._claims_schemas import Claim, ClaimsReport, DedupedClaim
from src.config import Settings
from src.services.embeddings import embed_texts
from src.utterances.schema import Utterance

DEFAULT_SIMILARITY_THRESHOLD = 0.85


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class _UnionFind:
    _parent: list[int]

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


async def dedupe_claims(
    claims: list[Claim],
    utterances: list[Utterance],
    settings: Settings,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> ClaimsReport:
    """Cluster claims by semantic similarity and compute prevalence stats.

    - `threshold`: cosine-similarity threshold above which two claims are
      considered duplicates. Default 0.85 (configurable per AC #3).
    - `utterances`: used to map `utterance_id` -> author for author_count /
      representative_authors.
    """
    if not claims:
        return ClaimsReport(deduped_claims=[], total_claims=0, total_unique=0)

    author_by_utterance: dict[str, str | None] = {}
    for utterance in utterances:
        if utterance.utterance_id:
            author_by_utterance[utterance.utterance_id] = utterance.author

    texts = [c.claim_text for c in claims]
    vectors = await embed_texts(texts, settings)
    if len(vectors) != len(claims):
        raise RuntimeError(
            f"embed_texts returned {len(vectors)} vectors for {len(claims)} claims"
        )

    uf = _UnionFind(len(claims))
    for i in range(len(claims)):
        for j in range(i + 1, len(claims)):
            if _cosine(vectors[i], vectors[j]) >= threshold:
                uf.union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(claims)):
        root = uf.find(idx)
        clusters.setdefault(root, []).append(idx)

    deduped: list[DedupedClaim] = []
    for _, member_indices in clusters.items():
        members = [claims[i] for i in member_indices]
        canonical = max(members, key=lambda c: c.confidence)

        authors_seen: list[str] = []
        author_set: set[str] = set()
        utterance_ids: list[str] = []
        for claim in members:
            utterance_ids.append(claim.utterance_id)
            author = author_by_utterance.get(claim.utterance_id)
            if author and author not in author_set:
                author_set.add(author)
                authors_seen.append(author)

        deduped.append(
            DedupedClaim(
                canonical_text=canonical.claim_text,
                occurrence_count=len(members),
                author_count=len(author_set),
                utterance_ids=utterance_ids,
                representative_authors=authors_seen[:5],
            )
        )

    deduped.sort(key=lambda d: d.occurrence_count, reverse=True)

    return ClaimsReport(
        deduped_claims=deduped,
        total_claims=len(claims),
        total_unique=len(deduped),
    )
