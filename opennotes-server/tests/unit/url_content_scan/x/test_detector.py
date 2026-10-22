from __future__ import annotations

import pytest

from src.url_content_scan.x.detector import XStatusRef, detect_x_status_url

pytestmark = pytest.mark.unit


class TestDetectXStatusUrl:
    def test_detects_x_com_status_url(self) -> None:
        ref = detect_x_status_url("https://x.com/elonmusk/status/1234567890")
        assert ref is not None
        assert ref.post_id == "1234567890"
        assert ref.host == "x.com"
        assert ref.canonical_url == "https://x.com/i/status/1234567890"

    def test_detects_twitter_com_status_url(self) -> None:
        ref = detect_x_status_url("https://twitter.com/user/status/9876543210")
        assert ref is not None
        assert ref.post_id == "9876543210"
        assert ref.host == "twitter.com"
        assert ref.canonical_url == "https://x.com/i/status/9876543210"

    def test_detects_mobile_x_com_url(self) -> None:
        ref = detect_x_status_url("https://mobile.x.com/user/status/111222333")
        assert ref is not None
        assert ref.post_id == "111222333"
        assert ref.host == "x.com"

    def test_detects_www_x_com_url(self) -> None:
        ref = detect_x_status_url("https://www.x.com/user/status/444555666")
        assert ref is not None
        assert ref.post_id == "444555666"

    def test_detects_i_web_status_path(self) -> None:
        ref = detect_x_status_url("https://x.com/i/web/status/777888999")
        assert ref is not None
        assert ref.post_id == "777888999"

    def test_returns_none_for_non_x_url(self) -> None:
        assert detect_x_status_url("https://example.com/article") is None

    def test_returns_none_for_x_com_without_status_segment(self) -> None:
        assert detect_x_status_url("https://x.com/elonmusk") is None

    def test_returns_none_for_non_numeric_post_id(self) -> None:
        assert detect_x_status_url("https://x.com/user/status/not-a-number") is None

    def test_returns_none_for_x_com_home(self) -> None:
        assert detect_x_status_url("https://x.com/") is None

    def test_xstatusref_model(self) -> None:
        ref = XStatusRef(
            post_id="123",
            host="x.com",
            canonical_url="https://x.com/i/status/123",
        )
        assert ref.post_id == "123"
        assert ref.host == "x.com"
