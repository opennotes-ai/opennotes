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
from dataclasses import dataclass
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
_CORAL_TALK_ASSET_ID_RE = re.compile(r'"talkAssetId"\s*:\s*"([^"]+)"')


def _normalize_coral_state_blob(value: str) -> str:
    """Decode legacy HTML-escaped Coral state blobs into parseable text."""
    normalized = value
    for _ in range(2):
        next_value = html.unescape(normalized)
        if next_value == normalized:
            break
        normalized = next_value

    return (
        normalized.replace("&escapedquot;", '"')
        .replace("&#34;", '"')
        .replace("&quot;", '"')
    )


class CoralSignal(BaseModel):
    graphql_origin: str
    story_url: str
    iframe_src: str
    story_id: str | None = None
    supports_graphql: bool = True
    embed_origin: str | None = None
    env_origin: str | None = None


@dataclass
class _LatimesSignalCandidate:
    embed_origin: str
    env_origin: str
    story_id: str
    has_coral_signal_marker: bool = False


class _CoralMarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._iframe_data: list[dict[str, Any]] = []
        self._has_script_signal = False
        self._has_optional_signal = False
        self._has_static_script_signal = False
        self._latimes_signal_stack: list[_LatimesSignalCandidate] = []
        self._latimes_signals: list[_LatimesSignalCandidate] = []
        self._wapo_script_origins: list[str] = []
        self._has_wapo_comments_marker = False
        self._static_script_origins: list[str] = []
        self._canonical_urls: list[str] = []
        self._community_hostnames: list[str] = []
        self._canonical_urls_from_state: list[str] = []
        self._talk_asset_ids: list[str] = []
        self._in_script = False
        self._capture_script_data = False

    @property
    def has_signal(self) -> bool:
        return (
            self._has_script_signal
            or self._has_optional_signal
            or bool(self._latimes_signals)
            or bool(self._wapo_script_origins and self._has_wapo_comments_marker)
        )

    @property
    def iframe_data(self) -> list[dict[str, Any]]:
        return self._iframe_data

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attrs_map: dict[str, str | None] = {
            str(name).lower(): value for name, value in attrs if name is not None
        }
        if self._contains_optional_markers(attrs_map):
            self._has_optional_signal = True

        for value in attrs_map.values():
            if value is not None:
                self._collect_state_json_values(value)

        if normalized_tag == "script":
            self._handle_script_start(attrs_map)
            return

        if self._contains_wapo_comments_marker(attrs_map):
            self._has_wapo_comments_marker = True

        if normalized_tag == "ps-comments":
            signal = self._capture_latimes_signal(attrs_map)
            if signal is not None:
                self._latimes_signal_stack.append(signal)
            return

        if normalized_tag == "link":
            self._capture_canonical_if_present(attrs_map)
            return

        if normalized_tag == "iframe":
            src = attrs_map.get("src")
            if src is None:
                return

            entry = self._iframe_candidate(src)
            if entry is not None:
                self._iframe_data.append(entry)
            return

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_script = False
            self._capture_script_data = False
            return

        if tag.lower() == "ps-comments":
            if not self._latimes_signal_stack:
                return

            signal = self._latimes_signal_stack.pop()
            if not signal.has_coral_signal_marker:
                return

            if not signal.story_id:
                return

            self._latimes_signals.append(signal)

    def handle_data(self, data: str) -> None:
        if self._in_script and self._capture_script_data and data:
            text = _normalize_coral_state_blob(data)
            self._collect_state_json_values(text)

        if self._latimes_signal_stack and data and "show comments" in data.lower():
            self._latimes_signal_stack[-1].has_coral_signal_marker = True

    def latimes_signal(self) -> CoralSignal | None:
        if not self._latimes_signals:
            return None

        signal = self._latimes_signals[0]
        story_id = signal.story_id

        return CoralSignal(
            iframe_src=f"{signal.env_origin}/embed/stream?storyID={story_id}",
            graphql_origin=signal.env_origin,
            story_url=story_id,
            supports_graphql=False,
            story_id=story_id,
            embed_origin=signal.embed_origin,
            env_origin=signal.env_origin,
        )

    def static_signal(self) -> dict[str, str] | None:
        if not self._has_static_script_signal:
            return None

        canonical_url = self._first_valid_url(
            self._canonical_urls + self._canonical_urls_from_state
        )
        if not canonical_url:
            return None

        asset_id = self._first_value(self._talk_asset_ids)
        for community_host in self._community_hostnames:
            community_origin = self._canonical_to_origin(community_host)
            if not community_origin:
                continue

            matching_script_origin = self._matching_static_script_origin(community_origin)
            if not matching_script_origin:
                continue

            query_params = {"asset_url": canonical_url}
            if asset_id:
                query_params = {"asset_id": asset_id, "asset_url": canonical_url}

            return {
                "iframe_src": (
                    f"{matching_script_origin}/embed/stream?"
                    f"{urlencode(query_params)}"
                ),
                "graphql_origin": matching_script_origin,
                "story_url": canonical_url,
            }

        return None

    def wapo_signal(self) -> CoralSignal | None:
        if not self._has_wapo_comments_marker or not self._wapo_script_origins:
            return None

        canonical_url = self._first_valid_url(
            self._canonical_urls + self._canonical_urls_from_state
        )
        if not canonical_url:
            return None

        origin = self._wapo_script_origins[0]
        return CoralSignal(
            iframe_src=f"{origin}/embed/stream?{urlencode({'storyURL': canonical_url})}",
            graphql_origin=origin,
            story_url=canonical_url,
            supports_graphql=False,
            embed_origin=origin,
            env_origin=origin,
        )

    def _first_valid_url(self, candidates: list[str]) -> str | None:
        for candidate in candidates:
            parsed = urlparse(candidate)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return candidate
        return None

    @staticmethod
    def _first_value(candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate:
                return candidate
        return None

    def _collect_state_json_values(self, text: str) -> None:
        normalized = _normalize_coral_state_blob(text)
        for match in _CORAL_COMMUNITY_HOSTNAME_RE.finditer(normalized):
            self._community_hostnames.append(match.group(1))
        for match in _CORAL_CANONICAL_URL_RE.finditer(normalized):
            self._canonical_urls_from_state.append(match.group(1))
        for match in _CORAL_TALK_ASSET_ID_RE.finditer(normalized):
            self._talk_asset_ids.append(match.group(1))

    def _capture_canonical_if_present(self, attrs: dict[str, str | None]) -> None:
        rel = attrs.get("rel")
        href = attrs.get("href")
        if rel is None or href is None:
            return
        rel_values = rel.lower().split()
        if "canonical" in rel_values:
            self._canonical_urls.append(href)

    def _capture_latimes_signal(  # noqa: PLR0911
        self, attrs: dict[str, str | None]
    ) -> _LatimesSignalCandidate | None:
        if attrs.get("id") != "coral_talk_stream":
            return None

        data_embed_url = attrs.get("data-embed-url")
        data_env_url = attrs.get("data-env-url")
        story_id = (attrs.get("data-story-id") or "").strip()

        if not data_embed_url or not data_env_url or not story_id:
            return None

        embed_origin = self._parse_http_origin(data_embed_url)
        env_origin = self._parse_http_origin(data_env_url)
        if not embed_origin or not env_origin:
            return None

        parsed_embed = urlparse(data_embed_url)
        embed_host = parsed_embed.hostname
        if (
            not parsed_embed.path.endswith("/assets/js/embed.js")
            or embed_host is None
            or not self._is_coral_host(embed_host)
        ):
            return None

        parsed_env = urlparse(data_env_url)
        env_host = parsed_env.hostname
        if (
            env_host is None
            or not self._is_coral_host(env_host)
            or parsed_env.path not in {"", "/"}
        ):
            return None

        if embed_origin != env_origin:
            return None

        return _LatimesSignalCandidate(
            embed_origin=embed_origin,
            env_origin=env_origin,
            story_id=story_id,
        )

    def _handle_script_start(self, attrs: dict[str, str | None]) -> None:
        self._in_script = True
        src = attrs.get("src")
        self._capture_script_data = src is None

        self._has_script_signal = self._has_script_signal or self._script_src_matches(
            src
        )
        static_script_origin = self._static_script_src_origin(src)
        if static_script_origin is not None:
            self._has_static_script_signal = True
            self._static_script_origins.append(static_script_origin)
        wapo_script_origin = self._wapo_script_src_origin(src)
        if wapo_script_origin is not None:
            self._wapo_script_origins.append(wapo_script_origin)

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

    def _wapo_script_src_origin(self, src: str | None) -> str | None:
        if not src:
            return None

        parsed = urlparse(src)
        if (
            parsed.path != "/assets/js/embed.js"
            or parsed.hostname != "talk.washingtonpost.com"
        ):
            return None

        return self._parse_http_origin(src)

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

    def _contains_wapo_comments_marker(self, attrs: dict[str, str | None]) -> bool:
        data_testid = (attrs.get("data-testid") or "").lower()
        data_qa = (attrs.get("data-qa") or "").lower()
        node_id = (attrs.get("id") or "").lower()
        return (
            data_testid == "coral-comments"
            or data_qa == "comments-embed"
            or (node_id == "comments" and data_qa == "coral-comments")
        )

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

    def _parse_http_origin(self, candidate: str) -> str | None:
        parsed = urlparse(candidate)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            try:
                port = parsed.port
            except ValueError:
                return None
            port_suffix = f":{port}" if port is not None else ""
            return f"{parsed.scheme}://{parsed.hostname.lower()}{port_suffix}"
        return None

    @staticmethod
    def _is_coral_host(hostname: str) -> bool:
        host = hostname.lower()
        return host == "coral.coralproject.net" or host.endswith(
            ".coral.coralproject.net"
        )


def detect_coral(html: str) -> CoralSignal | None:  # noqa: PLR0911
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
        try:
            return CoralSignal(**parser.iframe_data[0])
        except Exception:
            return None

    if static_signal is not None:
        try:
            return CoralSignal(
                graphql_origin=static_signal["graphql_origin"],
                story_url=static_signal["story_url"],
                iframe_src=static_signal["iframe_src"],
            )
        except Exception:
            return None

    wapo_signal = parser.wapo_signal()
    if wapo_signal is not None:
        return wapo_signal

    return parser.latimes_signal()
