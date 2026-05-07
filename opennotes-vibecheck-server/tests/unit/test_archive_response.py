from __future__ import annotations

from src.routes.frame import _archive_response

_EXPECTED_DISPLAY_RULE = "img,video,iframe{max-width:100%;height:auto}"


def test_archive_response_injects_defensive_stylesheet() -> None:
    response = _archive_response("<html><body></body></html>")

    assert _EXPECTED_DISPLAY_RULE.encode() in bytes(response.body)


def test_archive_response_stylesheet_precedes_html() -> None:
    response = _archive_response("<html><body>content</body></html>")

    body = bytes(response.body).decode("utf-8")
    assert "<style>" in body
    assert "<html>" in body
    assert body.index("<style>") < body.index("<html>")


def test_archive_response_headers() -> None:
    response = _archive_response("<html></html>")

    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-store, private"
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_archive_response_stylesheet_is_wrapped_in_style_tag() -> None:
    response = _archive_response("<html></html>")

    body = bytes(response.body).decode("utf-8")
    assert f"<style>{_EXPECTED_DISPLAY_RULE}</style>" in body
