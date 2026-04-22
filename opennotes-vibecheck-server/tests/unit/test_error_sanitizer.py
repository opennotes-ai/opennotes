"""Tests for src.utils.error_sanitizer — redact PII, secrets, and signed URLs.

Each test exercises one behavior of `_sanitize` or `sanitize_processor`. Inputs
and expected outputs are written inline (DAMP) so that a failure message
immediately reveals which pattern regressed.
"""
from __future__ import annotations

import pytest

from src.utils.error_sanitizer import _sanitize, sanitize_processor


class TestSanitizePaths:
    def test_user_home_path_is_redacted(self) -> None:
        assert _sanitize("/Users/mike/secret.env -> error") == "<redacted>secret.env -> error"

    def test_linux_home_path_is_redacted(self) -> None:
        assert _sanitize("crash at /home/deploy/foo.py") == "crash at <redacted>foo.py"

    def test_user_home_path_with_nested_segments_redacts_user_prefix(self) -> None:
        """Per brief spec, `/Users/.+?/` is non-greedy — redacts `/Users/<username>/`
        but leaves deeper path segments intact so the filename is still debuggable.
        """
        result = _sanitize("see /Users/alice/work/proj/main.py")
        assert "/Users/alice/" not in result
        assert "main.py" in result
        assert "<redacted>" in result


class TestSanitizeBearerAndAuth:
    def test_bearer_token_is_redacted(self) -> None:
        result = _sanitize("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
        assert result == "Authorization: <redacted>"

    def test_auth_url_is_redacted(self) -> None:
        result = _sanitize("calling https://login.example.com/auth/callback?code=abc now")
        assert "<redacted>" in result
        assert "login.example.com" not in result
        assert "code=abc" not in result

    def test_http_auth_url_is_redacted(self) -> None:
        result = _sanitize("oidc http://idp.local/oauth2/auth/token failed")
        assert "<redacted>" in result
        assert "oauth2/auth/token" not in result


class TestSanitizeGCPProject:
    def test_gcp_project_id_is_redacted(self) -> None:
        assert _sanitize("project=google-mpf-abc.com") == "project=<redacted>"

    def test_gcp_project_id_embedded_is_redacted(self) -> None:
        result = _sanitize("host google-mpf-prod-123.com returned 500")
        assert "<redacted>" in result
        assert "google-mpf-prod-123.com" not in result


class TestSanitizeSignedUrls:
    def test_first_key_x_amz_signature_is_redacted(self) -> None:
        result = _sanitize("GET https://s3/bucket/key?X-Amz-Signature=ZZZ&foo=1")
        assert "X-Amz-Signature=ZZZ" not in result
        assert "ZZZ" not in result
        assert "foo=1" in result
        assert "<redacted>" in result

    def test_mid_query_x_goog_signature_is_redacted(self) -> None:
        """Regression guard: mid-query signature keys (after `&`) must redact.

        A naive implementation that anchors on `?` would miss this case and leak
        the signature value.
        """
        result = _sanitize("download https://storage/obj?foo=1&X-Goog-Signature=abcDEF123")
        assert "abcDEF123" not in result
        assert "X-Goog-Signature=abcDEF123" not in result
        assert "foo=1" in result
        assert "<redacted>" in result

    def test_mid_query_x_amz_signature_is_redacted(self) -> None:
        result = _sanitize("https://s3/obj?foo=bar&X-Amz-Signature=ZZZ&baz=qux")
        assert "ZZZ" not in result
        assert "foo=bar" in result
        assert "baz=qux" in result

    def test_mid_query_token_is_redacted(self) -> None:
        result = _sanitize("https://api/thing?page=2&token=SEKRET123")
        assert "SEKRET123" not in result
        assert "page=2" in result

    def test_first_key_token_is_redacted(self) -> None:
        result = _sanitize("https://api/thing?token=SEKRET123&page=2")
        assert "SEKRET123" not in result
        assert "page=2" in result

    def test_mid_query_sign_param_is_redacted(self) -> None:
        result = _sanitize("https://cdn/x?foo=1&sign=ABCDEF")
        assert "ABCDEF" not in result
        assert "foo=1" in result


class TestSanitizeExceptionInput:
    def test_sanitize_accepts_exception(self) -> None:
        exc = ValueError("/Users/mike/oops.py failed")
        result = _sanitize(exc)
        assert "/Users/mike/" not in result
        assert "<redacted>" in result
        assert "oops.py failed" in result

    def test_sanitize_accepts_plain_string(self) -> None:
        assert _sanitize("hello world") == "hello world"


class TestSanitizeProcessor:
    def test_processor_redacts_string_values_in_event_dict(self) -> None:
        event_dict = {
            "event": "download failed",
            "url": "https://s3/obj?foo=1&X-Amz-Signature=ZZZ",
            "count": 3,
        }
        out = sanitize_processor(None, "info", event_dict)
        assert out["event"] == "download failed"
        assert "ZZZ" not in out["url"]
        assert out["count"] == 3

    def test_processor_redacts_bearer_in_message(self) -> None:
        event_dict = {"event": "Authorization: Bearer eyJhbGciO"}
        out = sanitize_processor(None, "warning", event_dict)
        assert "eyJhbGciO" not in out["event"]
        assert "<redacted>" in out["event"]

    def test_processor_leaves_non_string_values_untouched(self) -> None:
        payload = {"event": "ok", "items": [1, 2, 3], "flag": True}
        out = sanitize_processor(None, "info", payload)
        assert out["items"] == [1, 2, 3]
        assert out["flag"] is True


@pytest.mark.parametrize(
    ("raw", "must_not_contain"),
    [
        ("/Users/mike/.env", "/Users/mike/"),
        ("/home/deploy/app.log", "/home/deploy/"),
        ("Bearer eyJhbGciOiJIUzI1NiJ9", "eyJhbGciOiJIUzI1NiJ9"),
        ("project google-mpf-prod.com down", "google-mpf-prod.com"),
        ("https://login.example.com/auth", "login.example.com"),
        ("https://x/y?foo=1&X-Amz-Signature=ZZZ", "ZZZ"),
        ("https://x/y?foo=1&X-Goog-Signature=ZZZ", "ZZZ"),
        ("https://x/y?foo=1&token=ZZZ", "token=ZZZ"),
        ("https://x/y?foo=1&sign=ZZZ", "sign=ZZZ"),
    ],
)
def test_sanitize_strips_known_pii_patterns(raw: str, must_not_contain: str) -> None:
    result = _sanitize(raw)
    assert must_not_contain not in result
    assert "<redacted>" in result
