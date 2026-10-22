from __future__ import annotations

from math import ceil, log2, sqrt

from src.url_content_scan.claims_schemas import ClaimCategory, ClaimsReport, DedupedClaim


def _cluster(
    text: str,
    *,
    category: ClaimCategory = ClaimCategory.SUBJECTIVE,
    occurrence_count: int,
    author_count: int,
) -> DedupedClaim:
    return DedupedClaim(
        canonical_text=text,
        category=category,
        occurrence_count=occurrence_count,
        author_count=author_count,
        utterance_ids=[f"u-{i}" for i in range(occurrence_count)],
        representative_authors=[f"author-{i}" for i in range(author_count)],
    )


def test_compute_highlights_empty_input_returns_empty_report() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    report = compute_highlights([], total_authors=0, total_utterances=0, settings=Settings())

    assert report.highlights == []
    assert report.total_input_count == 0
    assert report.floor_eligible_count == 0
    assert report.fallback_engaged is False


def test_compute_highlights_filters_to_subjective_and_self_claims() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    clusters = [
        _cluster(
            "subjective 1", category=ClaimCategory.SUBJECTIVE, occurrence_count=5, author_count=3
        ),
        _cluster(
            "self claim 1", category=ClaimCategory.SELF_CLAIMS, occurrence_count=5, author_count=3
        ),
        _cluster(
            "factual 1",
            category=ClaimCategory.POTENTIALLY_FACTUAL,
            occurrence_count=100,
            author_count=50,
        ),
    ]

    report = compute_highlights(
        clusters, total_authors=100, total_utterances=1000, settings=Settings()
    )

    assert report.total_input_count == 2
    texts = {h.cluster.canonical_text for h in report.highlights}
    assert "factual 1" not in texts


def test_compute_highlights_hard_floor_requires_author_count_gte_2_and_occurrences_gte_3() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    clusters = [
        _cluster(
            "below floor authors",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=5,
            author_count=1,
        ),
        _cluster(
            "below floor occurrences",
            category=ClaimCategory.SUBJECTIVE,
            occurrence_count=2,
            author_count=3,
        ),
        _cluster(
            "meets floor", category=ClaimCategory.SUBJECTIVE, occurrence_count=3, author_count=2
        ),
    ]

    report = compute_highlights(
        clusters, total_authors=10, total_utterances=50, settings=Settings()
    )

    assert report.floor_eligible_count == 1
    assert report.highlights[0].cluster.canonical_text == "meets floor"


def test_compute_highlights_scaled_survivors_preferred_over_floor_fallback() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    settings = Settings()
    total_authors = 200
    total_utterances = 1000

    scaled_min_authors = ceil(
        sqrt(max(total_authors, 0)) / settings.URL_SCAN_OPINIONS_HIGHLIGHTS_AUTHOR_DIVISOR
    )
    scaled_min_occ = ceil(
        log2(max(total_utterances, 2)) * settings.URL_SCAN_OPINIONS_HIGHLIGHTS_OCCURRENCE_MULTIPLIER
    )
    min_authors = max(2, scaled_min_authors)
    min_occ = max(3, scaled_min_occ)

    floor_only = _cluster(
        "floor only cluster",
        category=ClaimCategory.SUBJECTIVE,
        occurrence_count=3,
        author_count=2,
    )
    scaled_survivor = _cluster(
        "scaled survivor",
        category=ClaimCategory.SUBJECTIVE,
        occurrence_count=min_occ + 5,
        author_count=min_authors + 2,
    )

    report = compute_highlights(
        [floor_only, scaled_survivor],
        total_authors=total_authors,
        total_utterances=total_utterances,
        settings=settings,
    )

    assert report.fallback_engaged is False
    assert len(report.highlights) == 1
    assert report.highlights[0].cluster.canonical_text == "scaled survivor"
    assert report.highlights[0].crossed_scaled_threshold is True


def test_compute_highlights_fallback_when_no_scaled_survivors() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    settings = Settings()
    floor_eligible = _cluster(
        "floor eligible only",
        category=ClaimCategory.SUBJECTIVE,
        occurrence_count=4,
        author_count=2,
    )

    report = compute_highlights(
        [floor_eligible],
        total_authors=6,
        total_utterances=20,
        settings=settings,
    )

    assert report.fallback_engaged is True
    assert len(report.highlights) == 1
    assert report.highlights[0].cluster.canonical_text == "floor eligible only"
    assert report.highlights[0].crossed_scaled_threshold is False


def test_compute_highlights_threshold_info_populated_correctly() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import compute_highlights

    report = compute_highlights(
        [],
        total_authors=50,
        total_utterances=300,
        settings=Settings(),
    )

    assert report.threshold.total_authors == 50
    assert report.threshold.total_utterances == 300
    assert report.threshold.min_authors_required >= 2
    assert report.threshold.min_occurrences_required >= 3


def test_compute_highlights_from_claims_report() -> None:
    from src.config import Settings
    from src.url_content_scan.analyses.opinions.highlights import run_highlights

    claims = ClaimsReport(
        deduped_claims=[
            _cluster(
                "big opinion",
                category=ClaimCategory.SUBJECTIVE,
                occurrence_count=20,
                author_count=10,
            ),
            _cluster(
                "small fact",
                category=ClaimCategory.POTENTIALLY_FACTUAL,
                occurrence_count=100,
                author_count=50,
            ),
        ],
        total_claims=2,
        total_unique=2,
    )

    report = run_highlights(
        claims_report=claims,
        total_authors=20,
        total_utterances=100,
        settings=Settings(),
    )

    assert report.total_input_count == 1
    assert report.highlights[0].cluster.canonical_text == "big opinion"
