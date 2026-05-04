from __future__ import annotations

from src.url_content_scan.html_sanitize import strip_noise


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
