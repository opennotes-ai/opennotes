from __future__ import annotations

import re
from collections.abc import Sequence

from bs4 import BeautifulSoup
from bs4.element import Tag

from src.utterances.schema import Utterance

_BLOCK_TAGS = {
    "article",
    "blockquote",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "p",
    "section",
}
_WHITESPACE_RE = re.compile(r"\s+")


def _normalized_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _candidate_text(element: Tag) -> str:
    return _normalized_text(element.get_text(" ", strip=True))


def _depth(element: Tag) -> int:
    depth = 0
    parent = element.parent
    while isinstance(parent, Tag):
        depth += 1
        parent = parent.parent
    return depth


def annotate_utterances_in_html(
    html: str,
    utterances: Sequence[Utterance],
) -> str:
    if not utterances:
        return html

    soup = BeautifulSoup(html, "html.parser")
    candidates = [
        element
        for element in soup.find_all(_BLOCK_TAGS)
        if isinstance(element, Tag) and _candidate_text(element)
    ]
    candidates.sort(key=lambda element: (len(_candidate_text(element)), -_depth(element)))
    used_elements = {
        id(element)
        for element in candidates
        if element.has_attr("data-utterance-id")
    }
    existing_ids = {
        str(element["data-utterance-id"])
        for element in candidates
        if element.has_attr("data-utterance-id")
    }

    for utterance in utterances:
        utterance_id = utterance.utterance_id
        utterance_text = _normalized_text(utterance.text)
        if not utterance_id or not utterance_text or utterance_id in existing_ids:
            continue

        for element in candidates:
            if id(element) in used_elements:
                continue
            if utterance_text not in _candidate_text(element):
                continue
            element["data-utterance-id"] = utterance_id
            used_elements.add(id(element))
            existing_ids.add(utterance_id)
            break

    return str(soup)
