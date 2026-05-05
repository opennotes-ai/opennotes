from __future__ import annotations

import pytest

from src.url_content_scan.coral import CoralSignal, detect_coral

pytestmark = pytest.mark.unit


def test_detects_coral_signal_from_tier1_html() -> None:
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

    assert detect_coral(html) == CoralSignal(
        graphql_origin="https://coral.npr.org",
        story_url="https://www.npr.org/2026/04/29/example",
        iframe_src="https://coral.npr.org/embed/stream?storyURL=https%3A%2F%2Fwww.npr.org%2F2026%2F04%2F29%2Fexample",
    )


def test_detects_coral_signal_from_data_embed_coral_shape() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.example.com/science/2026/05/04/story" />
        <script src="https://comments.example.org/assets/js/embed.js"></script>
      </head>
      <body>
        <div data-embed-coral="true" id="comments-root"></div>
      </body>
    </html>
    """

    assert detect_coral(html) == CoralSignal(
        graphql_origin="https://comments.example.org",
        story_url="https://www.example.com/science/2026/05/04/story",
        iframe_src="https://comments.example.org/embed/stream?storyURL=https%3A%2F%2Fwww.example.com%2Fscience%2F2026%2F05%2F04%2Fstory",
        supports_graphql=False,
        embed_origin="https://comments.example.org",
        env_origin="https://comments.example.org",
    )


def test_detects_coral_signal_from_latimes_ps_comments_shape() -> None:
    html = """
    <html>
      <body>
        <ps-comments
          id="coral_talk_stream"
          data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
          data-env-url="https://latimes.coral.coralproject.net"
          data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
        >Show Comments</ps-comments>
      </body>
    </html>
    """

    signal = detect_coral(html)

    assert isinstance(signal, CoralSignal)
    assert signal.graphql_origin == "https://latimes.coral.coralproject.net"
    assert signal.story_id == "0000019d-ccf9-ddcd-adfd-deff9ae80000"
    assert signal.supports_graphql is False
    assert signal.env_origin == "https://latimes.coral.coralproject.net"
    assert signal.embed_origin == "https://latimes.coral.coralproject.net"
    assert signal.story_url == "0000019d-ccf9-ddcd-adfd-deff9ae80000"
    assert (
        signal.iframe_src == "https://latimes.coral.coralproject.net/embed/stream?storyID="
        "0000019d-ccf9-ddcd-adfd-deff9ae80000"
    )


@pytest.mark.parametrize(
    "html",
    [
        "<html><body><article>plain article</article></body></html>",
        """
        <html><body>
          <iframe src="https://example.com/embed/stream?storyID=123"></iframe>
        </body></html>
        """,
        "<html><body><script>broken",
    ],
)
def test_detect_coral_returns_none_for_non_matches(html: str) -> None:
    assert detect_coral(html) is None
