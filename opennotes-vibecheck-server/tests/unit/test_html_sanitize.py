from __future__ import annotations

from src.utils.html_sanitize import (
    extract_archive_main_content,
    strip_for_display,
    strip_for_llm,
)

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
