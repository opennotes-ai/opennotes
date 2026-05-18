from src.x.detector import detect_x_status_url


def test_detects_x_status_url_without_query() -> None:
    ref = detect_x_status_url("https://x.com/jack/status/20")

    assert ref is not None
    assert ref.post_id == "20"
    assert ref.host == "x.com"
    assert ref.canonical_url == "https://x.com/i/status/20"


def test_detects_twitter_status_url_and_strips_suffixes() -> None:
    ref = detect_x_status_url("https://twitter.com/jack/status/20/photo/1?s=21")

    assert ref is not None
    assert ref.post_id == "20"
    assert ref.host == "twitter.com"
    assert ref.canonical_url == "https://x.com/i/status/20"


def test_detects_mobile_and_i_web_status_urls() -> None:
    mobile = detect_x_status_url("mobile.twitter.com/jack/status/20")
    web = detect_x_status_url("https://x.com/i/web/status/1234567890")

    assert mobile is not None
    assert mobile.post_id == "20"
    assert web is not None
    assert web.post_id == "1234567890"


def test_rejects_non_status_routes_and_lookalike_hosts() -> None:
    assert detect_x_status_url("https://x.com/jack") is None
    assert detect_x_status_url("https://x.com/i/lists/123") is None
    assert detect_x_status_url("https://x.com/jack/status/20abc") is None
    assert detect_x_status_url("https://evil-x.com/jack/status/20") is None
    assert detect_x_status_url("https://x.com.attacker.com/jack/status/20") is None
