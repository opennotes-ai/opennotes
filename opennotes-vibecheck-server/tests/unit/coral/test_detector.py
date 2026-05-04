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
        signal.iframe_src
        == "https://latimes.coral.coralproject.net/embed/stream?storyID="
        "0000019d-ccf9-ddcd-adfd-deff9ae80000"
    )


def test_detects_coral_signal_from_generic_render_only_coral_comments_shape() -> None:
    html = """
    <html>
      <head>
        <link
          rel="canonical"
          href="https://www.news.example/world/2026/05/04/does-it-work/"
        />
        <script
          src="https://comments.example.org/assets/js/embed.js?token=1725896287"
          id="comments-stream"
        ></script>
      </head>
      <body>
        <div data-testid="coral-comments">
          <div id="comments-wrapper" data-qa="comments-embed">
            <div class="wpds-light" data-qa="coral-comments" id="comments"></div>
          </div>
        </div>
      </body>
    </html>
    """

    signal = detect_coral(html)

    assert signal == CoralSignal(
        graphql_origin="https://comments.example.org",
        story_url=(
            "https://www.news.example/world/2026/05/04/"
            "does-it-work/"
        ),
        iframe_src=(
            "https://comments.example.org/embed/stream?storyURL="
            "https%3A%2F%2Fwww.news.example%2Fworld%2F2026%2F05%2F04%2Fdoes-it-work%2F"
        ),
        supports_graphql=False,
        embed_origin="https://comments.example.org",
        env_origin="https://comments.example.org",
    )


def test_detects_washington_post_shape_via_generic_render_only_coral_detection() -> None:
    html = """
    <html>
      <head>
        <link
          rel="canonical"
          href="https://www.washingtonpost.com/world/2026/05/04/us-ships-iran-hormuz-ceasefire/"
        />
        <script
          src="https://talk.washingtonpost.com/assets/js/embed.js?token=1725896287"
          id="comments-stream"
        ></script>
      </head>
      <body>
        <div data-testid="coral-comments">
          <div id="comments-wrapper" data-qa="comments-embed">
            <div class="wpds-light" data-qa="coral-comments" id="comments"></div>
          </div>
        </div>
      </body>
    </html>
    """

    signal = detect_coral(html)

    assert signal == CoralSignal(
        graphql_origin="https://talk.washingtonpost.com",
        story_url=(
            "https://www.washingtonpost.com/world/2026/05/04/"
            "us-ships-iran-hormuz-ceasefire/"
        ),
        iframe_src=(
            "https://talk.washingtonpost.com/embed/stream?storyURL="
            "https%3A%2F%2Fwww.washingtonpost.com%2Fworld%2F2026%2F05%2F04%2F"
            "us-ships-iran-hormuz-ceasefire%2F"
        ),
        supports_graphql=False,
        embed_origin="https://talk.washingtonpost.com",
        env_origin="https://talk.washingtonpost.com",
    )


def test_detects_coral_signal_from_generic_render_only_static_embed_shape() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.example.com/science/2026/05/04/story"/>
        <script src="https://static-coral.example.com/static/embed.js"></script>
      </head>
      <body>
        <div class="coral-comments-shell" data-coral-comments></div>
      </body>
    </html>
    """

    signal = detect_coral(html)
    assert signal == CoralSignal(
        graphql_origin="https://static-coral.example.com",
        story_url="https://www.example.com/science/2026/05/04/story",
        iframe_src="https://static-coral.example.com/embed/stream?storyURL=https%3A%2F%2Fwww.example.com%2Fscience%2F2026%2F05%2F04%2Fstory",
        supports_graphql=False,
        embed_origin="https://static-coral.example.com",
        env_origin="https://static-coral.example.com",
    )


def test_detects_mother_jones_style_inline_config_signal() -> None:
    html = """
    <html>
      <body>
        <div id="coral_thread"></div>
        <a id="coral-display-comments" href="#comment-container">view comments</a>
        <script>
          var mj_comment_config = {
            "storyID":"1201099",
            "storyURL":"https://www.motherjones.com/?p=1201099#comment-container",
            "root_URL":"motherjones.coral.coralproject.net",
            "static_URL":"motherjones.coral.coralproject.net"
          };
        </script>
      </body>
    </html>
    """

    signal = detect_coral(html)

    assert signal == CoralSignal(
        graphql_origin="https://motherjones.coral.coralproject.net",
        story_url="https://www.motherjones.com/?p=1201099#comment-container",
        story_id="1201099",
        iframe_src="https://motherjones.coral.coralproject.net/embed/stream?storyID=1201099",
        supports_graphql=False,
        embed_origin="https://motherjones.coral.coralproject.net",
        env_origin="https://motherjones.coral.coralproject.net",
    )


def test_rejects_inline_coral_config_without_any_coral_marker() -> None:
    html = """
    <html>
      <body>
        <div id="comments"></div>
        <script>
          var mj_comment_config = {
            "storyID":"1201099",
            "storyURL":"https://www.motherjones.com/?p=1201099#comment-container",
            "root_URL":"motherjones.coral.coralproject.net",
            "static_URL":"motherjones.coral.coralproject.net"
          };
        </script>
      </body>
    </html>
    """

    assert detect_coral(html) is None


@pytest.mark.parametrize(
    "html",
    [
        """
        <html>
          <body>
            <div id="coral-thread"></div>
            <script>
              var mj_comment_config = {
                "storyID":"1201099",
                "storyURL":"https://www.motherjones.com/?p=1201099#comment-container",
                "root_URL":"javascript:void(0)",
                "static_URL":"javascript:void(0)"
              };
            </script>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <div id="coral-thread"></div>
            <script>
              var mj_comment_config = {
                "root_URL":"motherjones.coral.coralproject.net",
                "static_URL":"motherjones.coral.coralproject.net"
              };
            </script>
          </body>
        </html>
        """,
    ],
)
def test_rejects_inline_coral_config_without_usable_story_or_origin(html: str) -> None:
    assert detect_coral(html) is None


@pytest.mark.parametrize(
    "html",
    [
        """
        <html>
          <head>
            <link rel="canonical" href="https://www.example.com/story"/>
            <script src="https://static-coral.example.org/assets/js/embed.js"></script>
          </head>
        </html>
        """,
        """
        <html>
          <head>
            <link rel="canonical" href="/relative/story"/>
            <script src="https://static-coral.example.org/assets/js/embed.js"></script>
            <div data-testid="coral-comments"></div>
          </head>
        </html>
        """,
        """
        <html>
          <head>
            <script src="https://static-coral.example.org/assets/js/embed.js"></script>
            <div data-coral-comments></div>
          </head>
        </html>
        """,
        """
        <html>
          <head>
            <link rel="canonical" href="https://www.example.com/story"/>
            <script src="https://static-coral.example.org/assets/js/embed.js"></script>
          </head>
          <body>
            <div data-qa="comments-embed"></div>
          </body>
        </html>
        """,
    ],
)
def test_rejects_render_only_shape_without_coral_guardrails(html: str) -> None:
    assert detect_coral(html) is None


def test_detects_coral_signal_from_valid_iframe_with_ps_comments_optional_marker() -> None:
    html = """
    <html>
      <body>
        <ps-comments id="coral_talk_stream" class="coral-talk-stream">
          Show Comments
        </ps-comments>
        <iframe
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


def test_detects_static_embed_with_talk_asset_id_in_escaped_props() -> None:
    html = """
    <html>
      <head>
        <link rel="canonical" href="https://www.tagesspiegel.de/2026/04/29/example"/>
        <script src="https://coral.tagesspiegel.de/static/embed.js"></script>
        <div data-hydrate-props="{&amp;escapedquot;talkAssetId&amp;escapedquot;:&amp;escapedquot;15538543&amp;escapedquot;,&amp;escapedquot;communityHostname&amp;escapedquot;:&amp;escapedquot;coral.tagesspiegel.de&amp;escapedquot;,&amp;escapedquot;canonicalUrl&amp;escapedquot;:&amp;escapedquot;https://www.tagesspiegel.de/2026/04/29/example&amp;escapedquot;}" />
      </head>
    </html>
    """

    signal = detect_coral(html)
    assert signal == CoralSignal(
        graphql_origin="https://coral.tagesspiegel.de",
        story_url="https://www.tagesspiegel.de/2026/04/29/example",
        iframe_src="https://coral.tagesspiegel.de/embed/stream?asset_id=15538543&asset_url=https%3A%2F%2Fwww.tagesspiegel.de%2F2026%2F04%2F29%2Fexample",
    )


@pytest.mark.parametrize(
    "html",
    [
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="latimes.coral.coralproject.net/assets/js/embed.js"
              data-env-url="https://latimes.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net/other/path.js"
              data-env-url="https://latimes.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
              data-env-url="https://other.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
              data-env-url="https://latimes.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            ><button>open</button></ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net/assets/js/embed.js"
              data-env-url="ftp://latimes.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="ftp://latimes.coral.coralproject.net/assets/js/embed.js"
              data-env-url="https://latimes.coral.coralproject.net"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net@attacker.example/assets/js/embed.js"
              data-env-url="https://latimes.coral.coralproject.net@attacker.example"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
        """
        <html>
          <body>
            <ps-comments
              id="coral_talk_stream"
              data-embed-url="https://latimes.coral.coralproject.net.attacker.example/assets/js/embed.js"
              data-env-url="https://latimes.coral.coralproject.net.attacker.example"
              data-story-id="0000019d-ccf9-ddcd-adfd-deff9ae80000"
            >Show Comments</ps-comments>
          </body>
        </html>
        """,
    ],
)
def test_rejects_malformed_latimes_ps_comments_urls(html: str) -> None:
    # Explicitly assert malformed values are rejected and do not produce partial signals.
    assert detect_coral(html) is None


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
