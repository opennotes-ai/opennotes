from __future__ import annotations

from src.url_content_scan.html_sanitize import (
    enrich_display_with_raw_styles,
    extract_archive_main_content,
    strip_for_display,
    strip_noise,
)


def test_strip_noise_removes_script_style_link_and_comments() -> None:
    value = (
        "<div>keep</div>"
        "<script>alert(1)</script>"
        "<STYLE>.x { color: red; }</STYLE>"
        "<!--hidden-->"
        '<link rel="stylesheet" href="/app.css">'
        "<p>stay</p>"
    )

    got = strip_noise(value)

    assert got is not None
    assert "<script" not in got.lower()
    assert "<style" not in got.lower()
    assert "<link" not in got.lower()
    assert "<!--" not in got
    assert "<div>keep</div>" in got
    assert "<p>stay</p>" in got


def test_strip_noise_preserves_none_and_empty_string() -> None:
    assert strip_noise(None) is None
    assert strip_noise("") == ""


def test_strip_for_display_removes_script_preserves_style() -> None:
    html = (
        "<html><head>"
        "<style>.x { color: red; }</style>"
        '<link rel="stylesheet" href="https://cdn.example/app.css">'
        "</head><body>"
        "<script>alert(1)</script>"
        "<!--hidden comment-->"
        "<p>keep this</p>"
        "</body></html>"
    )
    result = strip_for_display(html)
    assert result is not None
    assert "<script" not in result.lower()
    assert "<!--" not in result
    assert "<style" in result.lower()
    assert "<link" in result.lower()
    assert "<p>keep this</p>" in result


def test_strip_for_display_handles_none_and_empty() -> None:
    assert strip_for_display(None) is None
    assert strip_for_display("") == ""


def test_strip_for_display_strips_scroll_lock_overflow_style() -> None:
    html = '<html style="overflow:hidden;color:red"><body class="modal-open no-scroll"><p>text</p></body></html>'
    result = strip_for_display(html)
    assert result is not None
    assert "overflow" not in result
    assert "color:red" in result
    assert "modal-open" not in result
    assert "no-scroll" not in result


def test_strip_for_display_bounds_unsized_icon_svg() -> None:
    html = '<html><body><svg viewBox="0 0 24 24"><path d="M0 0"/></svg></body></html>'
    result = strip_for_display(html)
    assert result is not None
    assert "width:1em" in result


def test_extract_archive_main_content_returns_none_for_empty_input() -> None:
    result = extract_archive_main_content(None, None)
    assert result is None

    result2 = extract_archive_main_content("", "")
    assert result2 is None


def test_extract_archive_main_content_strips_dangerous_tags() -> None:
    long_text = "This is a sample article. " * 20
    html = (
        f"<html><body>"
        f"<article><p>{long_text}</p></article>"
        f'<form action="/submit"><input type="text"/></form>'
        f"<script>alert(1)</script>"
        f'<a href="javascript:void(0)">click</a>'
        f"</body></html>"
    )
    result = extract_archive_main_content(html, None)
    if result is not None:
        assert "<script" not in result.lower()
        assert "<form" not in result.lower()
        assert "javascript:" not in result.lower()


def test_extract_archive_main_content_uses_markdown_fallback() -> None:
    long_markdown = "# Article\n\n" + (
        "This is a sample article with enough text to pass the threshold. " * 5
    )
    result = extract_archive_main_content(None, long_markdown)
    if result is not None:
        assert "<h1>" in result.lower() or "article" in result.lower()


def test_extract_archive_main_content_is_cached() -> None:
    long_text = "Sample article content. " * 20
    html = f"<html><body><article><p>{long_text}</p></article></body></html>"
    result1 = extract_archive_main_content(html, None)
    result2 = extract_archive_main_content(html, None)
    assert result1 is result2


def test_enrich_display_with_raw_styles_passthrough_when_no_raw_html() -> None:
    display = "<html><body><p>text</p></body></html>"
    result = enrich_display_with_raw_styles(display, None, base_url=None)
    assert result == display

    result2 = enrich_display_with_raw_styles(display, "", base_url=None)
    assert result2 == display


def test_enrich_display_with_raw_styles_injects_https_stylesheet() -> None:
    display = "<html><head></head><body><p>text</p></body></html>"
    raw = '<html><head><link rel="stylesheet" href="https://cdn.example.com/app.css"></head></html>'
    result = enrich_display_with_raw_styles(display, raw, base_url="https://example.com")
    assert "cdn.example.com/app.css" in result


def test_enrich_display_with_raw_styles_rejects_http_stylesheet() -> None:
    display = "<html><head></head><body><p>text</p></body></html>"
    raw = '<html><head><link rel="stylesheet" href="http://cdn.example.com/app.css"></head></html>'
    result = enrich_display_with_raw_styles(display, raw, base_url="https://example.com")
    assert "cdn.example.com/app.css" not in result


def test_enrich_display_with_raw_styles_is_idempotent() -> None:
    display = "<html><head></head><body><p>text</p></body></html>"
    raw = '<html><head><link rel="stylesheet" href="https://cdn.example.com/app.css"></head></html>'
    once = enrich_display_with_raw_styles(display, raw, base_url="https://example.com")
    twice = enrich_display_with_raw_styles(once, raw, base_url="https://example.com")
    assert once.count("cdn.example.com/app.css") == twice.count("cdn.example.com/app.css")
