from datetime import UTC, datetime

from src.x.api import XTweet
from src.x.synthesize import synthesize_x_scrape


def test_synthesize_x_scrape_builds_safe_scrape_result() -> None:
    root = XTweet(
        id="100",
        text="<script>alert(1)</script> & hello",
        author_id="1",
        author_handle="alice",
        author_name="Alice",
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=UTC),
        in_reply_to_status_id=None,
    )

    scrape = synthesize_x_scrape(
        root,
        "https://x.com/i/status/100",
        og_image_url="https://pbs.twimg.com/media/post.jpg",
    )

    assert scrape.html is not None
    assert 'data-utterance-id="100"' in scrape.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; hello" in scrape.html
    assert "<script>" not in scrape.html
    assert scrape.markdown == "# @alice (Alice)\n\n<script>alert(1)</script> & hello\n\n_2026-05-18T12:00:00+00:00_"
    assert scrape.metadata is not None
    assert scrape.metadata.model_extra is not None
    assert scrape.metadata.model_extra["platform"] == "x"
    assert scrape.metadata.model_extra["canonical_url"] == "https://x.com/i/status/100"
    assert scrape.metadata.model_extra["og:title"] == "@alice on X"
    assert scrape.metadata.model_extra["og:image"] == "https://pbs.twimg.com/media/post.jpg"
    assert scrape.screenshot is None
