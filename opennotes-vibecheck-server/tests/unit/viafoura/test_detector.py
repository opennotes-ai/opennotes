"""Viafoura embed detection tests."""

from __future__ import annotations

from src.coral import CoralSignal
from src.viafoura import ViafouraSignal, detect_viafoura

AP_NEWS_HTML = """
<!doctype html>
<html>
  <head>
    <script src="https://cdn.viafoura.net/entry/index.js" async></script>
    <meta name="vf:container_id" content="12a31037f3c9a94d3cb9fbcaaf84d94f" />
  </head>
  <body>
    <article>Article body.</article>
    <div id="ap-comments" class="viafoura" style="min-height:418px">
      <vf-conversations id="vf-conv" limit="4"></vf-conversations>
      <vf-trending-articles id="vf-trending" limit="2" sort="comments" vf-container-id="ap-comments"></vf-trending-articles>
    </div>
  </body>
</html>
"""


def test_detect_viafoura_returns_signal_from_ap_news_embed() -> None:
    signal = detect_viafoura(AP_NEWS_HTML)

    assert signal == ViafouraSignal(
        container_id="12a31037f3c9a94d3cb9fbcaaf84d94f",
        site_domain=None,
        embed_origin="https://cdn.viafoura.net",
        iframe_src=None,
        has_conversations_component=True,
    )


def test_detect_viafoura_returns_partial_signal_for_loader_script() -> None:
    html = '<script src="https://cdn.viafoura.net/entry/index.js"></script>'

    signal = detect_viafoura(html)

    assert signal == ViafouraSignal(
        container_id=None,
        site_domain=None,
        embed_origin="https://cdn.viafoura.net",
        iframe_src=None,
        has_conversations_component=False,
    )


def test_detect_viafoura_ignores_article_without_embed() -> None:
    assert detect_viafoura("<article>Only article text.</article>") is None


def test_detect_viafoura_ignores_coral_embed() -> None:
    coral = CoralSignal(
        graphql_origin="https://coral.example.com",
        story_url="https://example.com/story",
        iframe_src="https://coral.example.com/embed/stream?storyURL=https%3A%2F%2Fexample.com%2Fstory",
    )

    html = f'<iframe src="{coral.iframe_src}"></iframe>'

    assert detect_viafoura(html) is None
