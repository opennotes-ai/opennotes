from __future__ import annotations

from pathlib import Path
from typing import Any

from src.utils.html_sanitize import (
    extract_archive_main_content,
    strip_for_display,
    strip_for_llm,
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_la_times_archive_fixture() -> str:
    return (_FIXTURES_DIR / "archive_la_times_reduced.html").read_text(encoding="utf-8")

# A trimmed-down Mastodon-shaped SSR HTML: a long chunk of site chrome
# (search box, server stats, banner) precedes the actual post content.
# Browsers visit this without JS so the SPA never rehydrates — Firecrawl's
# only_main_content extractor keeps the whole shell because Mastodon's
# layout uses generic divs rather than semantic landmarks.
_MASTODON_SHAPED_HTML = """
<!doctype html>
<html lang="en"><head><title>Cory Doctorow on mamot.fr</title></head>
<body>
  <div id="mastodon">
    <div class="columns-area">
      <div class="column">
        <div class="search">
          <h4>Recent searches</h4>
          <p>No recent searches</p>
          <h4>Search options</h4>
          <p>Only available when logged in.</p>
        </div>
      </div>
      <div class="column">
        <div class="getting-started">
          <p><strong>mamot.fr</strong> is one of the many independent
             Mastodon servers you can use to participate in the fediverse.</p>
          <p>Mamot.fr est un serveur Mastodon francophone, geree par
             La Quadrature du Net.</p>
          <h4>Administered by:</h4>
          <p>La Quadrature du Net @LaQuadrature</p>
          <h4>Server stats:</h4>
          <p><strong>2.4K</strong> active users</p>
        </div>
      </div>
      <div class="column">
        <h1>Back</h1>
        <article class="status">
          <header><a href="/@pluralistic"><strong>Cory Doctorow</strong>
            @pluralistic@mamot.fr</a></header>
          <div class="status__content">
            <p>Today's threads (a thread)</p>
            <p>Inside: Bubbles are REALLY evil; and more!</p>
            <p>Archived at:
              <a href="https://pluralistic.net/2026/05/07/dump-the-pumpers/">
                https://pluralistic.net/2026/05/07/dump-the-pumpers/</a></p>
            <p>The 2026 Guelph Lecture on enshittification will explore how
               we can fix the internet by giving users back control.</p>
            <p>This is the actual post body, several paragraphs long, that
               needs to surface in the archive viewport instead of being
               pushed thousands of pixels below the fold by site chrome.</p>
          </div>
        </article>
      </div>
    </div>
  </div>
</body></html>
"""


def test_extract_archive_returns_post_text_first_for_spa_shaped_html() -> None:
    # AC: archive viewport for a Mastodon-shaped SSR document needs the
    # actual post text to appear before any chrome text in the response.
    result = extract_archive_main_content(_MASTODON_SHAPED_HTML, None)

    assert result is not None
    today_idx = result.find("Today's threads")
    server_idx = result.find("Server stats")
    recent_idx = result.find("Recent searches")
    assert today_idx >= 0, "post text missing from extraction"
    # Chrome text either dropped or pushed below the post text.
    assert server_idx == -1 or today_idx < server_idx
    assert recent_idx == -1 or today_idx < recent_idx


def test_extract_archive_falls_back_to_markdown_when_html_underperforms() -> None:
    # When the html-side extractor returns less than the substantial-content
    # threshold, the fallback path renders the cached markdown (which
    # Firecrawl already main-content-extracted) so callers still get a
    # usable archive view instead of nothing.
    markdown = "# Article\n\n" + ("Paragraph body. " * 40)

    result = extract_archive_main_content("<html><body></body></html>", markdown)

    assert result is not None
    assert "<h1>Article</h1>" in result
    assert "Paragraph body" in result


def test_extract_archive_returns_none_for_empty_inputs() -> None:
    assert extract_archive_main_content(None, None) is None
    assert extract_archive_main_content("", "") is None
    assert extract_archive_main_content("   ", "   ") is None


def test_extract_archive_returns_none_when_extraction_and_markdown_are_empty() -> None:
    # An HTML that has no extractable content and no markdown should
    # return None so the caller can fall through to strip_for_display
    # or 404 to the screenshot tab.
    assert extract_archive_main_content("<html><body></body></html>", None) is None


def test_extract_archive_rejects_trivial_markdown_below_threshold() -> None:
    # P2.4: trivial markdown ("tiny", a few words) shouldn't override the
    # caller's strip_for_display fallback. The same min-content threshold
    # that gates the trafilatura path must gate the markdown path.
    assert extract_archive_main_content(None, "tiny") is None
    assert extract_archive_main_content(None, "# T\n\nshort.") is None


def test_extract_archive_strips_javascript_hrefs_from_trafilatura_output() -> None:
    # P2.5: trafilatura keeps `<a href="javascript:...">` even with
    # default-src 'none' CSP guarding the iframe. Strip the dangerous
    # href as defense in depth so the rendered DOM never carries the
    # exploit gadget in the first place.
    html = (
        "<!doctype html><html><body><article>"
        + ("<p>Body text long enough to clear the main-content threshold "
           "comfortably so the extractor returns this article. " * 6)
        + "<p><a href=\"javascript:alert('xss')\">click</a></p>"
        + "</article></body></html>"
    )

    result = extract_archive_main_content(html, None)

    assert result is not None
    # The href attribute itself must be gone — substring check is enough
    # because the test fixture body text never mentions the scheme.
    assert "href=\"javascript:" not in result.lower()
    assert "href='javascript:" not in result.lower()


def test_extract_archive_strips_event_handler_attributes() -> None:
    # P2.5: inline event handlers like onclick should be stripped from
    # extracted output. CSP blocks script execution, but the markup
    # itself shouldn't carry the gadget.
    html = (
        "<!doctype html><html><body><article>"
        + ("<p>This article has substantial body text that comfortably "
           "exceeds the trafilatura main-content threshold so the extractor "
           "actually returns this content instead of falling through to the "
           "markdown branch. The danger we are guarding against is a stray "
           "event-handler attribute surviving extraction. " * 3)
        + "<p onclick=\"alert(1)\">click bait</p>"
        + "</article></body></html>"
    )

    result = extract_archive_main_content(html, None)

    assert result is not None
    assert "onclick" not in result.lower()


def test_extract_archive_caches_extraction_output() -> None:
    # P2.6: trafilatura is too slow to run synchronously per request
    # against 72h cache rows that haven't changed. Hot-path callers see
    # the same (cached_html, cached_markdown) tuple repeatedly, so a
    # functools.lru_cache wrapper keeps the second-and-later calls O(1).
    # This test patches trafilatura.extract to count invocations.
    from unittest.mock import patch as _patch

    html = (
        "<!doctype html><html><body><article>"
        + ("<p>Body text long enough to clear the main-content threshold "
           "comfortably so the renderer returns this article. " * 6)
        + "</article></body></html>"
    )

    # Drop any prior cache state from earlier tests in the file so the
    # call count below is the count this test caused.
    extract_archive_main_content.cache_clear()  # type: ignore[attr-defined]

    real_extract = __import__("trafilatura").extract
    calls = {"count": 0}

    def counting_extract(*args: Any, **kwargs: Any) -> Any:
        calls["count"] += 1
        return real_extract(*args, **kwargs)

    with _patch("src.utils.html_sanitize.trafilatura.extract", side_effect=counting_extract):
        first = extract_archive_main_content(html, None)
        second = extract_archive_main_content(html, None)
        third = extract_archive_main_content(html, None)

    assert first is not None
    assert first == second == third
    assert calls["count"] == 1, "expected lru_cache to elide repeat extractions"


def test_extract_archive_strips_meta_refresh_iframe_form_object() -> None:
    # P2.5: meta refresh, iframe, form, object/embed are CSP-blocked at
    # render but should not survive extraction either. The markdown
    # path is where these gadgets are most likely to survive (Firecrawl
    # markdown can preserve raw HTML), so this test exercises that
    # branch by passing markdown directly with substantial body text.
    markdown = (
        ("Body text long enough to clear the main-content threshold "
         "comfortably so the renderer returns this article. " * 6)
        + "\n\n<meta http-equiv=\"refresh\" content=\"0;url=https://evil.example\">"
        + "<form action=\"https://evil.example\"><input/></form>"
        + "<iframe src=\"https://evil.example\"></iframe>"
        + "<object data=\"https://evil.example\"></object>"
        + "<embed src=\"https://evil.example\">"
    )

    result = extract_archive_main_content(None, markdown)

    assert result is not None
    lowered = result.lower()
    assert "<form" not in lowered
    assert "<iframe" not in lowered
    assert "<object" not in lowered
    assert "<embed" not in lowered
    assert "http-equiv" not in lowered


def test_strip_for_display_preserves_stylesheets() -> None:
    html = (
        "<html><head>"
        "<link rel='stylesheet' href='/article.css'>"
        "<style>.hero{width:200px;height:150px}</style>"
        "</head><body><img class='hero' src='photo.jpg'></body></html>"
    )

    result = strip_for_display(html)

    assert result is not None
    assert '<link href="/article.css" rel="stylesheet"/>' in result
    assert "<style>.hero{width:200px;height:150px}</style>" in result
    assert '<img class="hero" src="photo.jpg"/>' in result


def test_strip_for_display_removes_scripts_and_comments() -> None:
    html = (
        "<html><body>"
        "<!-- tracking marker -->"
        "<script type='application/javascript'>alert('x')</script>"
        "<p>Article</p>"
        "</body></html>"
    )

    result = strip_for_display(html)

    assert result == "<html><body><p>Article</p></body></html>"


def test_strip_for_llm_removes_scripts_styles_links_and_comments() -> None:
    html = (
        "<html><head>"
        "<link rel='stylesheet' href='/article.css'>"
        "<style>.hero{width:200px;height:150px}</style>"
        "<script>alert('x')</script>"
        "</head><body><!-- hidden --><p>Article</p></body></html>"
    )

    result = strip_for_llm(html)

    assert result == "<html><head></head><body><p>Article</p></body></html>"


def test_sanitizers_preserve_none_and_empty_string_contract() -> None:
    assert strip_for_display(None) is None
    assert strip_for_llm(None) is None
    assert strip_for_display("") == ""
    assert strip_for_llm("") == ""


def test_sanitizers_are_idempotent_on_clean_html() -> None:
    html = "<article><h1>Headline</h1><p>Body copy</p></article>"

    assert strip_for_display(strip_for_display(html)) == html
    assert strip_for_llm(strip_for_llm(html)) == html


def test_strip_for_display_removes_body_overflow_hidden() -> None:
    html = "<html><body style='overflow: hidden; padding: 10px'><p>text</p></body></html>"

    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    body = soup.find("body")
    assert body is not None
    style = str(body.get("style") or "")
    assert "overflow" not in style
    assert "padding" in style


def test_strip_for_display_removes_lock_classes_keeps_others() -> None:
    html = "<html><body class='page-body met-panel-open has-contextual-navigation article-page'><p>text</p></body></html>"

    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    body = soup.find("body")
    assert body is not None
    classes = body.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    assert "page-body" in classes
    assert "article-page" in classes
    assert "met-panel-open" not in classes
    assert "has-contextual-navigation" not in classes


def test_strip_for_display_preserves_inner_overflow_hidden() -> None:
    html = "<html><body><div style='overflow: hidden; width: 100px'><p>text</p></div></body></html>"

    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    div = soup.find("div")
    assert div is not None
    assert "overflow: hidden" in (div.get("style") or "")


def test_la_times_fixture_neutralizes_scroll_locks() -> None:
    html = load_la_times_archive_fixture()
    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    body = soup.find("body")
    assert body is not None
    style = str(body.get("style") or "")
    assert "overflow" not in style
    classes = body.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    assert "met-panel-open" not in classes
    assert "has-contextual-navigation" not in classes


def test_strip_for_display_handles_empty_style_attribute_removal() -> None:
    html = "<html><body style='overflow: hidden'><p>text</p></body></html>"

    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    body = soup.find("body")
    assert body is not None
    assert body.get("style") is None


def test_strip_for_display_handles_overscroll_behavior_none() -> None:
    html = "<html><body style='overscroll-behavior: none'><p>text</p></body></html>"

    result = strip_for_display(html)

    assert result is not None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(result, "html.parser")
    body = soup.find("body")
    assert body is not None
    assert body.get("style") is None
