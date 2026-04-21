from __future__ import annotations

import pytest

from src.analyses.claims import dedupe as dedupe_mod
from src.analyses.claims._claims_schemas import Claim, ClaimsReport
from src.analyses.claims.dedupe import dedupe_claims
from src.config import Settings
from src.utterances.schema import Utterance


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _patch_embeddings(
    monkeypatch: pytest.MonkeyPatch, vectors_by_text: dict[str, list[float]]
) -> list[list[str]]:
    calls: list[list[str]] = []

    async def fake_embed_texts(texts: list[str], _settings):
        calls.append(list(texts))
        return [vectors_by_text[t] for t in texts]

    monkeypatch.setattr(dedupe_mod, "embed_texts", fake_embed_texts)
    return calls


async def test_three_paraphrases_cluster_to_one(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = [
        "it's going to rain today",
        "rain is coming today",
        "we should expect rain today",
    ]
    near_duplicate_vec = [1.0, 0.0, 0.0]
    _patch_embeddings(monkeypatch, dict.fromkeys(texts, near_duplicate_vec))

    claims = [
        Claim(claim_text=texts[0], utterance_id="post-0", confidence=0.70),
        Claim(claim_text=texts[1], utterance_id="comment-1", confidence=0.90),
        Claim(claim_text=texts[2], utterance_id="comment-2", confidence=0.80),
    ]
    utterances = [
        Utterance(utterance_id="post-0", kind="post", text=texts[0], author="alice"),
        Utterance(utterance_id="comment-1", kind="comment", text=texts[1], author="bob"),
        Utterance(utterance_id="comment-2", kind="comment", text=texts[2], author="alice"),
    ]

    report = await dedupe_claims(claims, utterances, settings)

    assert isinstance(report, ClaimsReport)
    assert report.total_claims == 3
    assert report.total_unique == 1
    assert len(report.deduped_claims) == 1

    cluster = report.deduped_claims[0]
    assert cluster.occurrence_count == 3
    assert cluster.canonical_text == texts[1]
    assert set(cluster.utterance_ids) == {"post-0", "comment-1", "comment-2"}
    assert cluster.author_count == 2
    assert set(cluster.representative_authors) == {"alice", "bob"}


async def test_three_unrelated_claims_stay_separate(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = [
        "the earth is round",
        "python is a programming language",
        "coffee grows in brazil",
    ]
    orthogonal = {
        texts[0]: [1.0, 0.0, 0.0],
        texts[1]: [0.0, 1.0, 0.0],
        texts[2]: [0.0, 0.0, 1.0],
    }
    _patch_embeddings(monkeypatch, orthogonal)

    claims = [
        Claim(claim_text=texts[0], utterance_id="post-0", confidence=0.9),
        Claim(claim_text=texts[1], utterance_id="post-1", confidence=0.9),
        Claim(claim_text=texts[2], utterance_id="post-2", confidence=0.9),
    ]
    utterances = [
        Utterance(utterance_id="post-0", kind="post", text=texts[0], author="a"),
        Utterance(utterance_id="post-1", kind="post", text=texts[1], author="b"),
        Utterance(utterance_id="post-2", kind="post", text=texts[2], author="c"),
    ]

    report = await dedupe_claims(claims, utterances, settings)

    assert report.total_claims == 3
    assert report.total_unique == 3
    assert {c.canonical_text for c in report.deduped_claims} == set(texts)
    assert all(c.occurrence_count == 1 for c in report.deduped_claims)
    assert all(c.author_count == 1 for c in report.deduped_claims)


async def test_mixed_clusters_respect_threshold(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Two near-duplicates + one unrelated = 2 clusters.
    texts = [
        "vaccines are safe",
        "vaccines are safe and effective",
        "the moon landing was real",
    ]
    vec_rain = [1.0, 0.0]
    vec_moon = [0.0, 1.0]
    _patch_embeddings(
        monkeypatch,
        {texts[0]: vec_rain, texts[1]: vec_rain, texts[2]: vec_moon},
    )

    claims = [
        Claim(claim_text=texts[0], utterance_id="u1", confidence=0.6),
        Claim(claim_text=texts[1], utterance_id="u2", confidence=0.95),
        Claim(claim_text=texts[2], utterance_id="u3", confidence=0.8),
    ]
    utterances = [
        Utterance(utterance_id="u1", kind="post", text=texts[0], author="x"),
        Utterance(utterance_id="u2", kind="comment", text=texts[1], author="y"),
        Utterance(utterance_id="u3", kind="reply", text=texts[2], author="z"),
    ]

    report = await dedupe_claims(claims, utterances, settings)

    assert report.total_claims == 3
    assert report.total_unique == 2
    largest = report.deduped_claims[0]
    assert largest.occurrence_count == 2
    assert largest.canonical_text == texts[1]
    singleton = report.deduped_claims[1]
    assert singleton.occurrence_count == 1
    assert singleton.canonical_text == texts[2]


async def test_threshold_is_configurable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # cos(45deg) ≈ 0.707 — below 0.85 default (stays separate), above 0.70 override (merges).
    vec_a = [1.0, 0.0]
    vec_b = [1.0, 1.0]
    texts = ["claim a", "claim b"]
    _patch_embeddings(monkeypatch, {texts[0]: vec_a, texts[1]: vec_b})

    claims = [
        Claim(claim_text=texts[0], utterance_id="u1", confidence=0.5),
        Claim(claim_text=texts[1], utterance_id="u2", confidence=0.5),
    ]
    utterances = [
        Utterance(utterance_id="u1", kind="post", text=texts[0], author="a"),
        Utterance(utterance_id="u2", kind="post", text=texts[1], author="b"),
    ]

    strict_report = await dedupe_claims(claims, utterances, settings)
    assert strict_report.total_unique == 2

    loose_report = await dedupe_claims(claims, utterances, settings, threshold=0.7)
    assert loose_report.total_unique == 1


async def test_empty_claims_returns_empty_report(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise AssertionError("embed_texts should not be called for empty input")

    monkeypatch.setattr(dedupe_mod, "embed_texts", _boom)

    report = await dedupe_claims([], [], settings)
    assert report.total_claims == 0
    assert report.total_unique == 0
    assert report.deduped_claims == []
