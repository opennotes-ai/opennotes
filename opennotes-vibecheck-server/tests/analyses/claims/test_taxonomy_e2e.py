from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analyses.claims import dedupe as dedupe_mod
from src.analyses.claims._claims_schemas import Claim, ClaimCategory
from src.analyses.claims.dedupe import dedupe_claims
from src.config import Settings
from src.utterances.schema import Utterance


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _fixture_path() -> Path:
    return (
        Path(__file__).parents[2]
        / "fixtures"
        / "claims"
        / "wealth_tax"
        / "fixtures.json"
    )


def _load_wealth_tax_fixture() -> tuple[list[Claim], list[Utterance], dict[str, list[float]]]:
    payload = json.loads(_fixture_path().read_text())
    return (
        [Claim(**row) for row in payload["claims"]],
        [Utterance(**row) for row in payload["utterances"]],
        {k: list(v) for k, v in payload["embeddings"].items()},
    )


def _patch_embeddings(
    monkeypatch: pytest.MonkeyPatch, vectors_by_text: dict[str, list[float]]
) -> None:
    async def fake_embed_texts(texts: list[str], _settings):
        return [vectors_by_text[text] for text in texts]

    monkeypatch.setattr(dedupe_mod, "embed_texts", fake_embed_texts)


def _categories_by_name(report) -> dict[ClaimCategory, list[int]]:
    buckets: dict[ClaimCategory, list[int]] = {}
    for claim in report.deduped_claims:
        buckets.setdefault(claim.category, []).append(claim.occurrence_count)
    return buckets


async def test_wealth_tax_5_way_taxonomy_deduplication(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims, utterances, vectors_by_text = _load_wealth_tax_fixture()
    _patch_embeddings(monkeypatch, vectors_by_text)

    report = await dedupe_claims(claims, utterances, settings)

    by_category = _categories_by_name(report)
    assert by_category[ClaimCategory.SUBJECTIVE] == [3]
    assert by_category[ClaimCategory.PREDICTIONS] == [2]

    factual_clusters = by_category[ClaimCategory.POTENTIALLY_FACTUAL]
    assert sorted(factual_clusters, reverse=True) == [2, 1]
    assert report.total_claims == 8
    assert report.total_unique == 4


async def test_prediction_claims_stay_predictions_not_subjective(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims, utterances, vectors_by_text = _load_wealth_tax_fixture()
    _patch_embeddings(monkeypatch, vectors_by_text)

    report = await dedupe_claims(claims, utterances, settings)

    devastation_clusters = [
        cluster
        for cluster in report.deduped_claims
        if "devastating" in cluster.canonical_text.lower()
        or "devastate" in cluster.canonical_text.lower()
    ]
    assert len(devastation_clusters) == 1
    (cluster,) = devastation_clusters
    assert cluster.category is ClaimCategory.PREDICTIONS
    assert cluster.occurrence_count >= 2


async def test_potentially_factual_deduping_unchanged(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims, utterances, vectors_by_text = _load_wealth_tax_fixture()
    _patch_embeddings(monkeypatch, vectors_by_text)

    factual_claims = [c for c in claims if c.category is ClaimCategory.POTENTIALLY_FACTUAL]
    factual_utterance_ids = {claim.utterance_id for claim in factual_claims}
    factual_utterances = [
        utterance for utterance in utterances if utterance.utterance_id in factual_utterance_ids
    ]

    report = await dedupe_claims(factual_claims, factual_utterances, settings)

    assert report.total_claims == len(factual_claims) == 3
    assert report.total_unique == 2
    assert sorted([claim.occurrence_count for claim in report.deduped_claims], reverse=True) == [
        2,
        1,
    ]
