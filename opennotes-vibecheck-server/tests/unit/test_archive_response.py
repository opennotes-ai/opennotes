from __future__ import annotations

from src.routes.frame import _ARCHIVE_DISPLAY_STYLES, _archive_response


def test_archive_response_injects_defensive_stylesheet() -> None:
    response = _archive_response("<html><body></body></html>")

    assert b"img,video,iframe{max-width:100%;height:auto}" in response.body


def test_archive_response_stylesheet_precedes_html() -> None:
    response = _archive_response("<html><body>content</body></html>")

    body = response.body.decode("utf-8")
    assert "<style>" in body
    assert "<html>" in body
    assert body.index("<style>") < body.index("<html>")


def test_archive_response_headers() -> None:
    response = _archive_response("<html></html>")

    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-store, private"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_archive_display_styles_constant_value() -> None:
    assert "img,video,iframe{max-width:100%;height:auto}" in _ARCHIVE_DISPLAY_STYLES
    assert _ARCHIVE_DISPLAY_STYLES.startswith("<style>")
    assert _ARCHIVE_DISPLAY_STYLES.endswith("</style>")
