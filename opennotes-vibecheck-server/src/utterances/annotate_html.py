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
_VISIBLE_ANCESTOR_ATTR = "data-vibecheck-utterance-ancestor"
_VISIBLE_STYLE_ATTR = "data-vibecheck-utterance-style"
_VISIBLE_STYLE = f"""
[{_VISIBLE_ANCESTOR_ATTR}] {{
  display: revert !important;
  visibility: visible !important;
  opacity: 1 !important;
  height: auto !important;
  max-height: none !important;
  overflow: visible !important;
}}
"""
_OPENWEB_CLASS_PREFIXES = ("spcv_",)
_HIDDEN_STYLE_PATTERNS = (
    "display:none",
    "visibility:hidden",
    "opacity:0",
    "height:0",
    "height:0px",
    "max-height:0",
    "max-height:0px",
)


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


def _ensure_visible_style(soup: BeautifulSoup) -> None:
    if soup.find("style", attrs={_VISIBLE_STYLE_ATTR: True}):
        return
    style = soup.new_tag("style")
    style[_VISIBLE_STYLE_ATTR] = ""
    style.string = _VISIBLE_STYLE
    if soup.head:
        soup.head.append(style)
        return
    soup.insert(0, style)


def _style_value(element: Tag) -> str:
    value = element.get("style", "")
    if isinstance(value, str):
        return value.lower().replace(" ", "")
    return ""


def _class_values(element: Tag) -> list[str]:
    value = element.get("class")
    if isinstance(value, str):
        return value.split()
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _has_reveal_cue(element: Tag) -> bool:
    style = _style_value(element)
    if any(pattern in style for pattern in _HIDDEN_STYLE_PATTERNS):
        return True

    id_value = str(element.get("id", "")).lower()
    if "openweb" in id_value:
        return True

    classes = [class_name.lower() for class_name in _class_values(element)]
    return any(
        class_name.startswith(_OPENWEB_CLASS_PREFIXES) or "openweb" in class_name
        for class_name in classes
    )


def _mark_visible_ancestors(element: Tag) -> bool:
    marked = False
    parent = element.parent
    while isinstance(parent, Tag) and parent.name not in {"html", "body"}:
        if _has_reveal_cue(parent):
            parent[_VISIBLE_ANCESTOR_ATTR] = ""
            marked = True
        parent = parent.parent
    return marked


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
    used_elements = {id(element) for element in candidates if element.has_attr("data-utterance-id")}
    existing_ids = {
        str(element["data-utterance-id"])
        for element in candidates
        if element.has_attr("data-utterance-id")
    }
    annotated_elements = [
        element for element in candidates if element.has_attr("data-utterance-id")
    ]

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
            annotated_elements.append(element)
            break

    if annotated_elements:
        marked_reveal_ancestor = False
        for element in annotated_elements:
            marked_reveal_ancestor = _mark_visible_ancestors(element) or marked_reveal_ancestor
        if marked_reveal_ancestor:
            _ensure_visible_style(soup)

    return str(soup)
