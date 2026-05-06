from __future__ import annotations

from src.analyses.claims._claims_schemas import ClaimCategory, DedupedClaim
from src.analyses.opinions import highlights as highlights_module
from src.config import Settings


def _cluster(
    canonical_text: str,
    *,
    category: ClaimCategory,
    occurrence_count: int,
    author_count: int,
    utterance_ids: list[str] | None = None,
    representative_authors: list[str] | None = None,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=canonical_text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=utterance_ids or ["u-1"],
        representative_authors=representative_authors or ["alice"],
    )


def test_compute_highlights_empty_input() -> None:
    settings = Settings()
    report = highlights_module.compute_highlights(
        [],
        total_authors=0,
        total_utterances=0,
        settings=settings,
    )

    assert report.total_input_count == 0
    assert report.floor_eligible_count == 0
    assert report.fallback_engaged is False
    assert report.highlights == []
    assert report.threshold.total_authors == 0
    assert report.threshold.total_utterances == 0
    assert report.threshold.min_authors_required == 2
    assert report.threshold.min_occurrences_required == 3


def test_compute_highlights_below_floor_returns_empty() -> None:
    settings = Settings()
    report = highlights_module.compute_highlights(
        [
            _cluster(
                "Opinion 1",
                category=ClaimCategory.SUBJECTIVE,
                occurrence_count=2,
                author_count=1,
            ),
            _cluster(
                "Opinion 2",
                category=ClaimCategory.SELF_CLAIMS,
                occurrence_count=2,
                author_count=1,
            ),
        ],
        total_authors=10,
        total_utterances=100,
        settings=settings,
    )

    assert report.total_input_count == 2
    assert report.floor_eligible_count == 0
    assert report.fallback_engaged is False
    assert report.highlights == []


def test_compute_highlights_fallback_when_no_scaled_survivors() -> None:
    settings = Settings()
    floor_cluster = _cluster(
        "Floor-eligible but fails scaled threshold",
        category=ClaimCategory.SUBJECTIVE,
        occurrence_count=5,
        author_count=3,
    )
    ignored_cluster = _cluster(
        "Not considered",
        category=ClaimCategory.POTENTIALLY_FACTUAL,
        occurrence_count=99,
        author_count=99,
    )

    report = highlights_module.compute_highlights(
        [floor_cluster, ignored_cluster],
        total_authors=4,
        total_utterances=12,
        settings=settings,
    )

    assert report.threshold.min_authors_required == 2
    assert report.threshold.min_occurrences_required == 6
    assert report.floor_eligible_count == 1
    assert report.fallback_engaged is True
    assert len(report.highlights) == 1
    highlight = report.highlights[0]
    assert highlight.crossed_scaled_threshold is False
    assert highlight.cluster == floor_cluster
    assert highlight.cluster.model_dump() == floor_cluster.model_dump()


def test_compute_highlights_returns_scaled_survivors_for_large_thread() -> None:
    settings = Settings()
    cluster = _cluster(
        "Large thread recurring opinion",
        category=ClaimCategory.SUBJECTIVE,
        occurrence_count=15,
        author_count=8,
    )

    report = highlights_module.compute_highlights(
        [cluster],
        total_authors=200,
        total_utterances=1000,
        settings=settings,
    )

    assert report.threshold.min_authors_required == 8
    assert report.threshold.min_occurrences_required == 15
    assert report.floor_eligible_count == 1
    assert report.fallback_engaged is False
    assert len(report.highlights) == 1
    assert report.highlights[0].crossed_scaled_threshold is True
    assert report.highlights[0].cluster == cluster


def test_compute_highlights_subjective_self_claim_sorting() -> None:
    settings = Settings()
    clusters = [
        _cluster(
            "Subj lower volume",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=24,
            author_count=20,
        ),
        _cluster(
            "Subj highest volume",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=48,
            author_count=25,
        ),
        _cluster(
            "Self claim ties on volume",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=40,
            author_count=18,
        ),
        _cluster(
            "Self claim with lower authors",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=40,
            author_count=20,
        ),
        _cluster(
            "Self lower volume",
            category=ClaimCategory.SELF_CLAIMS,
            occurrence_count=32,
            author_count=12,
        ),
    ]

    report = highlights_module.compute_highlights(
        clusters,
        total_authors=400,
        total_utterances=1200,
        settings=settings,
    )

    ranked = [highlight.cluster.canonical_text for highlight in report.highlights]
    assert ranked == [
        "Subj highest volume",
        "Subj lower volume",
        "Self claim with lower authors",
        "Self claim ties on volume",
        "Self lower volume",
    ]
    assert report.highlights[2].crossed_scaled_threshold is True


def test_compute_highlights_threshold_growth_is_sublinear() -> None:
    settings = Settings()

    small = highlights_module.compute_highlights(
        [],
        total_authors=400,
        total_utterances=100,
        settings=settings,
    )
    large = highlights_module.compute_highlights(
        [],
        total_authors=400,
        total_utterances=1000,
        settings=settings,
    )

    assert large.threshold.min_occurrences_required < small.threshold.min_occurrences_required * 10
