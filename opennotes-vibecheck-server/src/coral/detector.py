"""Pure Coral embed signature detection from Tier 1 HTML.

Heuristics used by this module are intentionally strict and anchored to known
Coral markers:

1. Script tag has a `src` containing either ``coralproject`` or
   ``coral.coralproject.net``.
2. Iframe `src` contains ``/embed/stream`` and has a `storyURL` query
   parameter with a usable URL.
3. Optional corroborating markers such as ``coral-talk-stream`` (class name)
   or ``data-embed-coral`` attributes are accepted but do not by themselves
   cause detection.

`detect_coral` returns `None` if signatures are partial, malformed, or
inconsistent.
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

_CORAL_SCRIPT_MARKERS = ("coralproject", "coral.coralproject.net")


class CoralSignal(BaseModel):
    graphql_origin: str
    story_url: str
    iframe_src: str


class _CoralMarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._iframe_data: list[dict[str, Any]] = []
        self._has_script_signal = False
        self._has_optional_signal = False

    @property
    def has_signal(self) -> bool:
        return self._has_script_signal or self._has_optional_signal

    @property
    def iframe_data(self) -> list[dict[str, Any]]:
        return self._iframe_data

    def handle_starttag(self, tag: str, attrs: list[tuple[str | None, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_map: dict[str, str | None] = {
            str(name).lower(): value for name, value in attrs if name is not None
        }

        if normalized_tag == "script":
            self._has_script_signal = self._has_script_signal or self._script_src_matches(
                attrs_map.get("src")
            )
            return

        if normalized_tag == "iframe":
            if self._contains_optional_markers(attrs_map):
                self._has_optional_signal = True

            src = attrs_map.get("src")
            if src is None:
                return

            entry = self._iframe_candidate(src)
            if entry is not None:
                self._iframe_data.append(entry)
            return

        if self._contains_optional_markers(attrs_map):
            self._has_optional_signal = True

    def _script_src_matches(self, src: str | None) -> bool:
        if not src:
            return False
        src_lower = src.lower()
        return any(marker in src_lower for marker in _CORAL_SCRIPT_MARKERS)

    def _contains_optional_markers(self, attrs: dict[str, str | None]) -> bool:
        if "data-embed-coral" in attrs:
            return True
        class_value = attrs.get("class")
        return bool(class_value and "coral-talk-stream" in class_value.lower())

    def _iframe_candidate(self, src: str) -> dict[str, str] | None:
        parsed = urlparse(src)
        if parsed.scheme == "" or parsed.netloc == "":
            return None
        path = parsed.path.lower()
        if "/embed/stream" not in path:
            return None

        params = parse_qs(parsed.query or "")
        story_url = self._extract_story_url(params)
        if not story_url:
            return None
        return {
            "iframe_src": src,
            "graphql_origin": f"{parsed.scheme}://{parsed.netloc}",
            "story_url": story_url,
        }

    def _extract_story_url(self, params: dict[str, list[str]]) -> str | None:
        # Prefer `storyURL` and reject `storyID`-only signals for now.
        for key in ("storyURL", "storyurl"):
            values = params.get(key)
            if values:
                story_url = values[0].strip()
                return story_url if story_url else None
        return None


def detect_coral(html: str) -> CoralSignal | None:
    """Return a `CoralSignal` when Coral markers and a usable stream iframe
    are both present; return `None` otherwise."""
    try:
        parser = _CoralMarkerParser()
        parser.feed(html)
        parser.close()
    except Exception:
        return None

    if not parser.has_signal:
        return None
    if not parser.iframe_data:
        return None

    signal = parser.iframe_data[0]
    try:
        return CoralSignal(**signal)
    except Exception:
        return None
