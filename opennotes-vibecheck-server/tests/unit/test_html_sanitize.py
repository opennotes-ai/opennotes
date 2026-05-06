from __future__ import annotations

from src.utils.html_sanitize import strip_for_display, strip_for_llm


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
