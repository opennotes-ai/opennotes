from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.schemas import PageKind
from src.url_content_scan.utterances.extractor import extract_utterances

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_case(name: str) -> dict:
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text())


@pytest.mark.unit
@pytest.mark.parametrize(
    "case_name",
    [
        "blog_post",
        "forum_thread",
        "hierarchical_thread",
        "blog_index",
        "article",
        "other",
    ],
)
def test_extract_utterances_matches_expected_fixture_shape(case_name: str) -> None:
    case = _load_case(case_name)

    payload = extract_utterances(
        ScrapeResult.model_validate(case["scrape"]),
        source_url=case["source_url"],
    )

    expected = case["expected"]
    assert payload.source_url == case["source_url"]
    assert payload.page_title == expected["page_title"]
    assert payload.page_kind is PageKind(expected["page_kind"])
    assert len(payload.utterances) == expected["utterance_count"]
    assert [item.kind for item in payload.utterances] == expected["kinds"]
    assert [item.parent_id for item in payload.utterances] == expected["parent_ids"]
    assert [item.author for item in payload.utterances] == expected["authors"]

    if "images" in expected:
        assert [item.mentioned_images for item in payload.utterances] == expected["images"]
    if "videos" in expected:
        assert [item.mentioned_videos for item in payload.utterances] == expected["videos"]
    if "urls" in expected:
        assert [item.mentioned_urls for item in payload.utterances] == expected["urls"]


@pytest.mark.unit
def test_extract_utterances_keeps_anchor_compatible_stable_ids() -> None:
    case = _load_case("hierarchical_thread")

    payload = extract_utterances(
        ScrapeResult.model_validate(case["scrape"]),
        source_url=case["source_url"],
    )

    assert [item.utterance_id for item in payload.utterances] == ["root-1", "reply-1", "reply-2"]
