"""TDD tests for pure Coral HTML signature detection.

Acceptance goals:

1. Return `CoralSignal` when a Coral embed can be parsed with both origin and
   story URL.
2. Return `None` for non-Coral content pages (HN, Reddit, plain articles).
3. Return `None` for malformed HTML rather than raising.
4. Return `None` when the Coral iframe is missing required attributes.
"""
from __future__ import annotations

import pytest

from src.coral import CoralSignal, detect_coral


def test_detects_coral_signal_from_tier1_html() -> None:
    """Signal is returned when script + iframe markers are present."""
    html = """
    <html>
      <head>
        <script src="https://assets.coralproject.net/assets/js/embed.js"></script>
      </head>
      <body>
        <iframe
          class="coral-talk-stream"
          src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fwww.npr.org%2F2026%2F04%2F29%2Fexample"
        ></iframe>
      </body>
    </html>
    """

    signal = detect_coral(html)
    assert signal == CoralSignal(
        graphql_origin="https://coral.npr.org",
        story_url="https://www.npr.org/2026/04/29/example",
        iframe_src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fwww.npr.org%2F2026%2F04%2F29%2Fexample",
    )


@pytest.mark.parametrize(
    "html",
    [
        "<html><body><div class='thing'>HN comments loaded here</div></body></html>",
        "<html><body><section class='comments'>Reddit discussion</section></body></html>",
        """
        <article class="BLOG_POST">
          <h1>Just a blog article</h1>
          <p>No comment embedding is present.</p>
        </article>
        """,
    ],
)
def test_rejects_non_coral_pages(html: str) -> None:
    assert detect_coral(html) is None


def test_returns_none_for_malformed_html() -> None:
    """Malformed markup does not crash and only succeeds with complete signals."""
    html = (
        "<html><head><script src='https://assets.coralproject.net/embed.js'>"
        "<body><iframe src='https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fwww.npr.org%2Fbad"
    )

    assert detect_coral(html) is None


def test_returns_none_when_iframe_src_is_missing() -> None:
    html = """
    <html>
      <head>
        <script src="https://coral.coralproject.net/embed.js"></script>
      </head>
      <body>
        <iframe class="coral-talk-stream"></iframe>
      </body>
    </html>
    """
    assert detect_coral(html) is None
