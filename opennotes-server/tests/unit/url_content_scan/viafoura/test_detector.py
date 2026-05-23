from __future__ import annotations

import pytest

from src.url_content_scan.viafoura import ViafouraSignal, detect_viafoura

pytestmark = pytest.mark.unit


def test_detects_viafoura_signal_from_loader_script() -> None:
    html = """
    <html>
      <head>
        <script src="https://cdn.viafoura.net/entry/index.js"></script>
        <meta name="vf:container_id" content="abc123" />
        <meta name="vf:site_domain" content="example.com" />
      </head>
      <body><div class="viafoura">comments here</div></body>
    </html>
    """
    signal = detect_viafoura(html)
    assert signal is not None
    assert signal.platform == "viafoura"
    assert signal.container_id == "abc123"
    assert signal.site_domain == "example.com"
    assert signal.embed_origin == "https://cdn.viafoura.net"


def test_detects_viafoura_via_vf_conversations_tag() -> None:
    html = """
    <html>
      <head>
        <meta name="vf:container_id" content="ctr-001" />
      </head>
      <body>
        <vf-conversations></vf-conversations>
      </body>
    </html>
    """
    signal = detect_viafoura(html)
    assert signal is not None
    assert signal.has_conversations_component is True
    assert signal.container_id == "ctr-001"


def test_returns_none_when_no_viafoura_markers() -> None:
    html = """
    <html>
      <head><title>No comments here</title></head>
      <body><p>Some article text.</p></body>
    </html>
    """
    assert detect_viafoura(html) is None


def test_detects_viafoura_iframe() -> None:
    html = """
    <html>
      <body>
        <iframe src="https://embed.viafoura.com/embed/comments"></iframe>
      </body>
    </html>
    """
    signal = detect_viafoura(html)
    assert signal is not None
    assert signal.iframe_src == "https://embed.viafoura.com/embed/comments"


def test_signal_without_container_id_detected_via_class() -> None:
    html = """
    <html>
      <body>
        <div class="viafoura comments-widget">Loading...</div>
      </body>
    </html>
    """
    signal = detect_viafoura(html)
    assert signal is not None
    assert signal.container_id is None


def test_returns_none_for_empty_html() -> None:
    assert detect_viafoura("") is None


def test_returns_none_for_short_html_no_markers() -> None:
    assert detect_viafoura("<html><body><p>Hello</p></body></html>") is None


def test_viafoura_signal_defaults() -> None:
    signal = ViafouraSignal()
    assert signal.platform == "viafoura"
    assert signal.embed_origin == "https://cdn.viafoura.net"
    assert signal.container_id is None
    assert signal.site_domain is None
