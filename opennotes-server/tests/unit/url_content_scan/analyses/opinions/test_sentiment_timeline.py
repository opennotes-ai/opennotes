from __future__ import annotations

from src.url_content_scan.opinions_schemas import SentimentStatsReport
from src.url_content_scan.schemas import SectionSlug


def test_sentiment_stats_report_has_no_extra_fields_beyond_schema() -> None:
    report = SentimentStatsReport(
        per_utterance=[],
        positive_pct=0.0,
        negative_pct=0.0,
        neutral_pct=100.0,
        mean_valence=0.0,
    )
    dumped = report.model_dump()
    assert "per_utterance" in dumped
    assert "positive_pct" in dumped
    assert "negative_pct" in dumped
    assert "neutral_pct" in dumped
    assert "mean_valence" in dumped


def test_section_slug_has_trends_and_highlights() -> None:
    assert hasattr(SectionSlug, "OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS")
    assert hasattr(SectionSlug, "OPINIONS_SENTIMENTS_HIGHLIGHTS")
    assert (
        SectionSlug.OPINIONS_SENTIMENTS_TRENDS_OPPOSITIONS.value
        == "opinions_sentiments__trends_oppositions"
    )
    assert SectionSlug.OPINIONS_SENTIMENTS_HIGHLIGHTS.value == "opinions_sentiments__highlights"
