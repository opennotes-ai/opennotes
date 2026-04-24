"""Per-utterance media attribution by parsing sanitized HTML.

`attribute_media` mutates a list of Utterance objects in place, populating
`mentioned_urls`, `mentioned_images`, and `mentioned_videos` by finding the
nearest ancestor DOM region whose text prefix-matches the utterance.

`page_level_media` synthesizes a deduplicated union across all utterances for
downstream Web Risk + image/video section workers.
"""
from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from src.cache.normalize import normalize_url

from .schema import Utterance

YT_DLP_IFRAME_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "youtu.be",
        "vimeo.com",
        "player.vimeo.com",
    }
)

_TEXT_PREFIX_LEN = 120


def _norm(text: str) -> str:
    return " ".join(text.split())


def _text_prefix(tag: Tag) -> str:
    return _norm(tag.get_text(" ", strip=True))[:_TEXT_PREFIX_LEN]


def _utterance_prefix(utterance: Utterance) -> str:
    return _norm(utterance.text)[:_TEXT_PREFIX_LEN]


def _find_matching_utterance(
    element: Tag,
    utterances: list[Utterance],
) -> Utterance | None:
    """Walk ancestors of `element` looking for a text prefix match."""
    for ancestor in element.parents:
        if not isinstance(ancestor, Tag):
            continue
        ancestor_prefix = _text_prefix(ancestor)
        if not ancestor_prefix:
            continue
        for utterance in utterances:
            utt_prefix = _utterance_prefix(utterance)
            if not utt_prefix:
                continue
            if ancestor_prefix.startswith(utt_prefix) or utt_prefix.startswith(
                ancestor_prefix
            ):
                return utterance
    return None


def _append_unique(lst: list[str], value: str) -> None:
    if value and value not in lst:
        lst.append(value)


def _canonical_media_url(value: str) -> str:
    return normalize_url(value.strip())


def _is_video_iframe(src: str) -> bool:
    try:
        host = urlparse(src).hostname or ""
    except Exception:
        return False
    return host in YT_DLP_IFRAME_HOSTS


def attribute_media(  # noqa: PLR0912
    html: str,
    utterances: list[Utterance],
) -> None:
    """Mutate utterances in place: fill mentioned_urls/images/videos.

    Walk every <a>, <img>, <video>, <source>, <iframe> in the parsed DOM.
    For each media element, find the nearest ancestor whose text (first 120
    chars, whitespace-normalized) prefix-matches an utterance's text
    (whitespace-normalized, first 120 chars). Attribute to that utterance.

    Elements with no matching region are attributed to the first utterance
    of kind="post" as a best-effort fallback (so page-level Web Risk + image
    moderation always have a non-empty pool for the primary post).

    If html is empty/None: return immediately, no mutation.
    """
    if not html or not html.strip():
        return
    if not utterances:
        return

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return

    first_post = next(
        (u for u in utterances if u.kind == "post"),
        utterances[0] if utterances else None,
    )

    for tag in soup.find_all(["a", "img", "video", "source", "iframe"]):
        if not isinstance(tag, Tag):
            continue

        tag_name = tag.name

        if tag_name == "a":
            href = tag.get("href", "")
            if not isinstance(href, str) or not href.strip():
                continue
            target = _find_matching_utterance(tag, utterances) or first_post
            if target is not None:
                _append_unique(target.mentioned_urls, href.strip())

        elif tag_name == "img":
            src = tag.get("src", "")
            if not isinstance(src, str) or not src.strip():
                continue
            target = _find_matching_utterance(tag, utterances) or first_post
            if target is not None:
                _append_unique(target.mentioned_images, src.strip())

        elif tag_name == "video":
            src = tag.get("src", "")
            if isinstance(src, str) and src.strip():
                target = _find_matching_utterance(tag, utterances) or first_post
                if target is not None:
                    _append_unique(target.mentioned_videos, src.strip())

        elif tag_name == "source":
            src = tag.get("src", "")
            if not isinstance(src, str) or not src.strip():
                continue
            parent = tag.parent
            if isinstance(parent, Tag) and parent.name == "video":
                target = _find_matching_utterance(tag, utterances) or first_post
                if target is not None:
                    _append_unique(target.mentioned_videos, src.strip())
            else:
                target = _find_matching_utterance(tag, utterances) or first_post
                if target is not None:
                    _append_unique(target.mentioned_images, src.strip())

        elif tag_name == "iframe":
            src = tag.get("src", "")
            if not isinstance(src, str) or not src.strip():
                continue
            if _is_video_iframe(src.strip()):
                target = _find_matching_utterance(tag, utterances) or first_post
                if target is not None:
                    _append_unique(target.mentioned_videos, src.strip())


def page_level_media(utterances: list[Utterance]) -> dict[str, list[str]]:
    """Synthesize deduplicated page-level unions from all utterances.

    Used by Web Risk + image/video section workers. Returns a dict with
    sorted, deduplicated lists for "urls", "images", and "videos".
    """
    return {
        "urls": sorted({_canonical_media_url(u) for utt in utterances for u in utt.mentioned_urls}),
        "images": sorted({_canonical_media_url(u) for utt in utterances for u in utt.mentioned_images}),
        "videos": sorted({_canonical_media_url(u) for utt in utterances for u in utt.mentioned_videos}),
    }
