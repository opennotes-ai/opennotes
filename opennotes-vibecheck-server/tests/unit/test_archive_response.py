from __future__ import annotations

from src.routes.frame import _archive_response

_EXPECTED_DISPLAY_RULE = "img{max-width:100%!important;height:auto!important}"


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
    content_security_policy = response.headers["content-security-policy"]
    assert "default-src 'none'" in content_security_policy
    assert "style-src 'unsafe-inline' https:" in content_security_policy


def test_archive_response_stylesheet_is_wrapped_in_style_tag() -> None:
    response = _archive_response("<html></html>")

    body = bytes(response.body).decode("utf-8")
    assert body.startswith("<style>")
    assert _EXPECTED_DISPLAY_RULE in body
    assert "</style><html>" in body


def test_archive_response_preserves_doctype_first() -> None:
    response = _archive_response("<!doctype html><html><body></body></html>")

    body = bytes(response.body)
    assert body[: len(b"<!doctype html>")].lower() == b"<!doctype html>"
    decoded = body.decode("utf-8")
    assert decoded.lower().index("<!doctype html>") < decoded.index("<style>")


def test_archive_response_without_doctype() -> None:
    response = _archive_response("<html><body></body></html>")

    body = bytes(response.body).decode("utf-8")
    assert body.index("<style>") < body.index("<html>")
