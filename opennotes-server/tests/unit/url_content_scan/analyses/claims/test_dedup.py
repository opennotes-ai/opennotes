from __future__ import annotations

import asyncio

import pytest

from src.url_content_scan.utterances.schema import Utterance


@pytest.mark.asyncio
async def test_run_claims_dedup_collapses_semantic_duplicates() -> None:
    from src.url_content_scan.analyses.claims.dedup import ExtractedClaim, run_claims_dedup

    utterances = [
        Utterance(utterance_id="u-1", kind="post", text="Rain is coming today.", author="alice"),
        Utterance(
            utterance_id="u-2",
            kind="comment",
            text="We should expect rain today.",
            author="bob",
        ),
        Utterance(
            utterance_id="u-3",
            kind="reply",
            text="It is going to rain today.",
            author="alice",
        ),
    ]

    async def fake_extract(utterance: Utterance) -> list[ExtractedClaim]:
        return [
            ExtractedClaim(
                claim_text=utterance.text,
                confidence={"u-1": 0.7, "u-2": 0.95, "u-3": 0.8}[utterance.utterance_id or ""],
            )
        ]

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    report = await run_claims_dedup(
        utterances,
        extract_claims=fake_extract,
        embed_texts=fake_embed,
    )

    assert report.total_claims == 3
    assert report.total_unique == 1
    assert len(report.deduped_claims) == 1
    cluster = report.deduped_claims[0]
    assert cluster.canonical_text == "We should expect rain today."
    assert cluster.occurrence_count == 3
    assert cluster.author_count == 2
    assert set(cluster.utterance_ids) == {"u-1", "u-2", "u-3"}
    assert set(cluster.representative_authors) == {"alice", "bob"}


@pytest.mark.asyncio
async def test_run_claims_dedup_bounds_per_utterance_extraction_concurrency() -> None:
    from src.url_content_scan.analyses.claims.dedup import run_claims_dedup

    utterances = [
        Utterance(utterance_id=f"u-{idx}", kind="comment", text=f"utterance {idx}")
        for idx in range(20)
    ]
    current = 0
    max_seen = 0

    async def fake_extract(_utterance: Utterance) -> list[object]:
        nonlocal current, max_seen
        current += 1
        max_seen = max(max_seen, current)
        await asyncio.sleep(0.01)
        current -= 1
        return []

    async def fake_embed(_texts: list[str]) -> list[list[float]]:
        raise AssertionError("embed_texts should not run when there are no claims")

    report = await run_claims_dedup(
        utterances,
        extract_claims=fake_extract,
        embed_texts=fake_embed,
    )

    assert report.total_claims == 0
    assert report.total_unique == 0
    assert max_seen <= 8
    assert max_seen == 8
