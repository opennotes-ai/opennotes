from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.url_content_scan.schemas import PageKind
from src.url_content_scan.utterances.schema import (
    Utterance,
    UtteranceAnchor,
    UtterancesPayload,
)


@pytest.mark.unit
def test_utterances_payload_uses_url_scan_page_kind_and_anchor_shape() -> None:
    payload = UtterancesPayload(
        source_url="https://example.com",
        scraped_at=datetime(2026, 5, 4, tzinfo=UTC),
        page_title="Example",
        page_kind=PageKind.FORUM_THREAD,
        utterances=[
            Utterance(
                utterance_id="root-1",
                kind="post",
                text="Root post",
            )
        ],
    )
    anchor = UtteranceAnchor(position=1, utterance_id="root-1")

    assert payload.page_kind is PageKind.FORUM_THREAD
    assert anchor.model_dump() == {"position": 1, "utterance_id": "root-1"}
