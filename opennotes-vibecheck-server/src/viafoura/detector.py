"""Pure Viafoura embed signature detection from page HTML."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel

_VIAFOURA_SCRIPT_HOST = "cdn.viafoura.net"
_VIAFOURA_ENTRY_PATH = "/entry/index.js"


class ViafouraSignal(BaseModel):
    platform: Literal["viafoura"] = "viafoura"
    container_id: str | None = None
    site_domain: str | None = None
    embed_origin: str = "https://cdn.viafoura.net"
    iframe_src: str | None = None
    has_conversations_component: bool = False


class _ViafouraMarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_loader_script = False
        self.has_viafoura_class = False
        self.has_conversations_component = False
        self.container_id: str | None = None
        self.site_domain: str | None = None
        self.embed_origin: str | None = None
        self.iframe_src: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_map: dict[str, str | None] = {
            str(name).lower(): value for name, value in attrs if name is not None
        }

        class_value = attrs_map.get("class")
        if class_value and "viafoura" in class_value.lower().split():
            self.has_viafoura_class = True

        if normalized_tag == "script":
            self._capture_script(attrs_map)
            return

        if normalized_tag == "meta":
            self._capture_meta(attrs_map)
            return

        if normalized_tag in {"vf-conversations", "vf-conversations-count"}:
            self.has_conversations_component = True

        if normalized_tag in {"vf-tray", "vf-tray-trigger", "vf-widget"}:
            self.has_viafoura_class = True

        if normalized_tag == "iframe":
            src = attrs_map.get("src")
            if src and "viafoura" in src.lower():
                self.iframe_src = src

    def _capture_script(self, attrs_map: dict[str, str | None]) -> None:
        src = attrs_map.get("src")
        if not src:
            return

        parsed = urlparse(src)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        if host == _VIAFOURA_SCRIPT_HOST and path.endswith(_VIAFOURA_ENTRY_PATH):
            self.has_loader_script = True
            self.embed_origin = f"{parsed.scheme or 'https'}://{host}"

    def _capture_meta(self, attrs_map: dict[str, str | None]) -> None:
        name = (attrs_map.get("name") or "").lower()
        content = attrs_map.get("content")
        if not content:
            return
        if name == "vf:container_id":
            self.container_id = content
        elif name in {"vf:site_domain", "vf:domain"}:
            self.site_domain = content

    def signal(self) -> ViafouraSignal | None:
        if not (
            self.has_loader_script
            or self.has_conversations_component
            or self.container_id
            or self.iframe_src
        ):
            return None

        return ViafouraSignal(
            container_id=self.container_id,
            site_domain=self.site_domain,
            embed_origin=self.embed_origin or "https://cdn.viafoura.net",
            iframe_src=self.iframe_src,
            has_conversations_component=self.has_conversations_component,
        )


def detect_viafoura(html: str) -> ViafouraSignal | None:
    """Return a Viafoura signal when page HTML exposes Viafoura markers."""
    if "viafoura" not in html.lower() and "vf:" not in html.lower():
        return None

    parser = _ViafouraMarkerParser()
    try:
        parser.feed(html)
    except Exception:
        return None
    return parser.signal()


__all__ = ["ViafouraSignal", "detect_viafoura"]
