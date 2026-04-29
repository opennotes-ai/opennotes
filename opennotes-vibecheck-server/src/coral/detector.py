"""Pure Coral embed signature detection from Tier 1 HTML.

Heuristics used by this module are intentionally strict and anchored to known
Coral markers:

1. Modern Coral Talk embeds expose a script tag with a `src` containing either
   ``coralproject`` or ``coral.coralproject.net`` plus an ``/embed/stream``
   iframe using ``storyURL``.
2. Older Coral Talk static embeds expose a script at ``/static/embed.js``
   alongside a community hostname and canonical article URL from page metadata.
3. Iframe `src` contains ``/embed/stream`` and has a `storyURL` query
   parameter with a usable URL.
4. Optional corroborating markers such as ``coral-talk-stream`` (class name)
   or ``data-embed-coral`` attributes are accepted but do not by themselves
   cause detection.

`detect_coral` returns `None` if signatures are partial, malformed, or
inconsistent.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from pydantic import BaseModel

_CORAL_SCRIPT_MARKERS = ("coralproject", "coral.coralproject.net")
_CORAL_STATIC_EMBED_MARKER = "/static/embed.js"
_CORAL_COMMUNITY_HOSTNAME_RE = re.compile(
    r'"communityHostname"\s*:\s*"([^"]+)"'
)
_CORAL_CANONICAL_URL_RE = re.compile(r'"canonicalUrl"\s*:\s*"([^"]+)"')


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
        self._has_static_script_signal = False
        self._static_script_origins: list[str] = []
        self._canonical_urls: list[str] = []
        self._community_hostnames: list[str] = []
        self._canonical_urls_from_state: list[str] = []
        self._in_script = False
        self._capture_script_data = False

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
            self._in_script = True
            src = attrs_map.get("src")
            self._capture_script_data = src is None

            self._has_script_signal = self._has_script_signal or self._script_src_matches(
                src
            )
            static_script_origin = self._static_script_src_origin(src)
            if static_script_origin is not None:
                self._has_static_script_signal = True
                self._static_script_origins.append(static_script_origin)
            return

        if normalized_tag == "link":
            self._capture_canonical_if_present(attrs_map)
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

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_script = False
            self._capture_script_data = False

    def handle_data(self, data: str) -> None:
        if self._in_script and self._capture_script_data and data:
            text = html.unescape(data)
            self._collect_state_json_values(text)

    def static_signal(self) -> dict[str, str] | None:
        if not self._has_static_script_signal:
            return None

        canonical_url = self._first_valid_url(
            self._canonical_urls + self._canonical_urls_from_state
        )
        if not canonical_url:
            return None

        for community_host in self._community_hostnames:
            community_origin = self._canonical_to_origin(community_host)
            if not community_origin:
                continue

            matching_script_origin = self._matching_static_script_origin(community_origin)
            if not matching_script_origin:
                continue

            return {
                "iframe_src": (
                    f"{matching_script_origin}/embed/stream?"
                    f"{urlencode({'asset_url': canonical_url})}"
                ),
                "graphql_origin": matching_script_origin,
                "story_url": canonical_url,
            }

        return None

    def _first_valid_url(self, candidates: list[str]) -> str | None:
        for candidate in candidates:
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return candidate
        return None

    def _collect_state_json_values(self, text: str) -> None:
        for match in _CORAL_COMMUNITY_HOSTNAME_RE.finditer(text):
            self._community_hostnames.append(match.group(1))
        for match in _CORAL_CANONICAL_URL_RE.finditer(text):
            self._canonical_urls_from_state.append(match.group(1))

    def _capture_canonical_if_present(self, attrs: dict[str, str | None]) -> None:
        rel = attrs.get("rel")
        href = attrs.get("href")
        if rel is None or href is None:
            return
        rel_values = rel.lower().split()
        if "canonical" in rel_values:
            self._canonical_urls.append(href)

    def _script_src_matches(self, src: str | None) -> bool:
        if not src:
            return False
        src_lower = src.lower()
        return any(marker in src_lower for marker in _CORAL_SCRIPT_MARKERS)

    def _static_script_src_origin(self, src: str | None) -> str | None:
        if not src:
            return None
        if _CORAL_STATIC_EMBED_MARKER not in src.lower():
            return None

        parsed = urlparse(src)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return None

    def _matching_static_script_origin(self, candidate: str) -> str | None:
        for origin in self._static_script_origins:
            if origin == candidate:
                return origin
        return None

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
                parsed = urlparse(story_url)
                if parsed.scheme in {"http", "https"} and parsed.netloc:
                    return story_url
                return None
        return None

    def _canonical_to_origin(self, candidate: str) -> str | None:
        value = candidate.strip()
        graphql_origin = None
        if value:
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                graphql_origin = f"{parsed.scheme}://{parsed.netloc}"
            elif "://" not in value:
                fallback = urlparse(f"//{value}")
                if (
                    fallback.scheme == ""
                    and fallback.path in {"", "/"}
                    and fallback.netloc
                ):
                    graphql_origin = f"https://{fallback.netloc}"
        return graphql_origin


def detect_coral(html: str) -> CoralSignal | None:
    """Return a `CoralSignal` when Coral markers and a usable stream iframe
    are both present; return `None` otherwise."""
    try:
        parser = _CoralMarkerParser()
        parser.feed(html)
        parser.close()
    except Exception:
        return None

    static_signal = parser.static_signal()
    if not parser.has_signal and static_signal is None:
        return None

    if parser.iframe_data:
        signal = parser.iframe_data[0]
    else:
        if static_signal is None:
            return None
        signal = static_signal

    try:
        return CoralSignal(**signal)
    except Exception:
        return None
