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


def test_detects_coral_signal_from_static_embed() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.tagesspiegel.de/2026/04/29/example"/>
        <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
        <script>
          window.__INITIAL_STATE__ = {"communityHostname":"coral.tagesspiegel.de"};
        </script>
      </head>
    </html>
    """

    signal = detect_coral(html)
    assert signal == CoralSignal(
        graphql_origin="https://coral.tagesspiegel.de",
        story_url="https://www.tagesspiegel.de/2026/04/29/example",
        iframe_src="https://coral.tagesspiegel.de/embed/stream?asset_url=https%3A%2F%2Fwww.tagesspiegel.de%2F2026%2F04%2F29%2Fexample",
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


def test_returns_none_when_static_embed_canonical_is_missing() -> None:
    html = """
    <html>
      <head>
        <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
        <script>
          window.__INITIAL_STATE__ = {"communityHostname":"coral.tagesspiegel.de"};
        </script>
      </head>
    </html>
    """
    assert detect_coral(html) is None


def test_returns_none_when_static_embed_community_host_is_unusable() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.tagesspiegel.de/2026/04/29/example"/>
        <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
        <script>
          window.__INITIAL_STATE__ = {"communityHostname":"ftp://coral.tagesspiegel.de"};
        </script>
      </head>
    </html>
    """
    assert detect_coral(html) is None


def test_rejects_static_embed_when_script_origin_does_not_match_community_host() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://example.com/story"/>
        <script src="https://cdn.example.com/static/embed.js"></script>
        <script>
          window.__INITIAL_STATE__ = {"communityHostname":"comments.example.com"};
        </script>
      </head>
    </html>
    """
    assert detect_coral(html) is None


def test_detects_static_embed_from_initial_state_canonical_url() -> None:
    html = """
    <html>
      <head>
        <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
        <script>
          window.__INITIAL_STATE__ = {"communityHostname":"coral.tagesspiegel.de","canonicalUrl":"https://www.tagesspiegel.de/2026/04/29/example"};
        </script>
      </head>
    </html>
    """

    signal = detect_coral(html)
    assert signal == CoralSignal(
        graphql_origin="https://coral.tagesspiegel.de",
        story_url="https://www.tagesspiegel.de/2026/04/29/example",
        iframe_src="https://coral.tagesspiegel.de/embed/stream?asset_url=https%3A%2F%2Fwww.tagesspiegel.de%2F2026%2F04%2F29%2Fexample",
    )


@pytest.mark.parametrize(
    "story_url",
    [
        "not-a-url",
        "/relative/path",
        "javascript:alert(1)",
    ],
)
def test_returns_none_when_story_url_is_not_http_url(story_url: str) -> None:
    html = f"""
    <html>
      <head>
        <script src="https://assets.coralproject.net/assets/js/embed.js"></script>
      </head>
      <body>
        <iframe
          class="coral-talk-stream"
          src="https://coral.npr.org/embed/stream?storyURL={story_url}"
        ></iframe>
      </body>
    </html>
    """

    assert detect_coral(html) is None
