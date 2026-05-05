from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha1
from html import unescape
from urllib.parse import unquote

from lxml import html as lxml_html
from lxml.html import HtmlElement

from src.services.firecrawl_client import ScrapeResult
from src.url_content_scan.coral import (
    CoralFetchError,
    CoralUnsupportedError,
    detect_coral,
    fetch_coral_comments,
    merge_coral_into_scrape,
)
from src.url_content_scan.schemas import PageKind
from src.utils.async_compat import run_sync

from .media_extraction import extract_image_urls, extract_video_urls, normalize_public_url
from .schema import Utterance, UtterancesPayload

_UTTERANCE_CONTAINER_XPATH = ".//*[@data-comment-id or @data-reply-id or @data-node-id or @data-entry-id or @data-role='post']"
_WHITESPACE_RE = re.compile(r"\s+")
_URL_TAG_RE = re.compile(r"<a\b[^>]*\bhref=[\"'](?P<url>[^\"']+)[\"']", re.IGNORECASE)
_CORAL_HEADER_RE = re.compile(
    r"^(?P<indent>\s*)- \[(?P<id>[^\]]+)\] author=(?P<author>\S+) "
    r"created_at=(?P<created_at>\S+) parent=(?P<parent>\S+)\s*$"
)


def extract_utterances(scrape: ScrapeResult, source_url: str) -> UtterancesPayload:
    scrape = _merge_coral_comments_if_available(scrape)
    root = _parse_html(scrape.html)
    page_kind = _classify_page_kind(scrape, root)
    page_title = _page_title(scrape, root)

    utterances = _extract_for_page_kind(page_kind, root, scrape, source_url)
    post_id = utterances[0].utterance_id if utterances and utterances[0].kind == "post" else None
    utterances.extend(_extract_coral_utterances(scrape, source_url, post_id=post_id))
    if not utterances:
        utterances = [_fallback_utterance(scrape, source_url)]

    return UtterancesPayload(
        source_url=source_url,
        scraped_at=datetime.now(UTC),
        utterances=utterances,
        page_title=page_title,
        page_kind=page_kind,
    )


def _parse_html(html_text: str | None) -> HtmlElement | None:
    if not html_text or not html_text.strip():
        return None
    try:
        return lxml_html.fromstring(html_text)
    except (TypeError, ValueError, lxml_html.ParserError):
        return None


def _page_title(scrape: ScrapeResult, root: HtmlElement | None) -> str | None:
    metadata = scrape.metadata
    if metadata and metadata.title:
        return metadata.title
    if root is None:
        return None
    for xpath in ("//h1[1]", "//title[1]", "//h2[1]"):
        matches = root.xpath(xpath)
        if matches:
            text = _clean_text(matches[0].text_content())
            if text:
                return text
    return None


def _classify_page_kind(scrape: ScrapeResult, root: HtmlElement | None) -> PageKind:
    metadata = scrape.metadata
    if metadata is not None:
        for key in ("page_kind", "pageKind"):
            raw = getattr(metadata, key, None)
            if isinstance(raw, str):
                page_kind = _coerce_page_kind(raw)
                if page_kind is not None:
                    return page_kind

    if root is None:
        return PageKind.OTHER

    raw_kind = root.xpath("string(//*[@data-page-kind][1]/@data-page-kind)")
    page_kind = _coerce_page_kind(raw_kind)
    if page_kind is not None:
        return page_kind

    inferred = PageKind.OTHER
    if root.xpath("//section[@data-comments]"):
        inferred = PageKind.BLOG_POST
    elif root.xpath("//*[@data-node-id and @data-parent-id]"):
        inferred = PageKind.HIERARCHICAL_THREAD
    elif len(root.xpath("//*[@data-entry-id]")) > 1:
        inferred = PageKind.BLOG_INDEX
    elif root.xpath("//*[@data-reply-id]") or root.xpath("//*[@data-role='post']"):
        inferred = PageKind.FORUM_THREAD
    elif root.xpath("//article"):
        inferred = PageKind.ARTICLE
    return inferred


def _coerce_page_kind(raw: str | None) -> PageKind | None:
    if not raw:
        return None
    try:
        return PageKind(raw.strip().lower())
    except ValueError:
        return None


def _extract_for_page_kind(
    page_kind: PageKind,
    root: HtmlElement | None,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    if root is None:
        return []

    if page_kind is PageKind.BLOG_POST:
        extractor = _extract_blog_post
    elif page_kind is PageKind.FORUM_THREAD:
        extractor = _extract_forum_thread
    elif page_kind is PageKind.HIERARCHICAL_THREAD:
        extractor = _extract_hierarchical_thread
    elif page_kind is PageKind.BLOG_INDEX:
        return _extract_blog_index(root, source_url)
    elif page_kind is PageKind.ARTICLE:
        extractor = _extract_article
    else:
        extractor = _extract_other
    return extractor(root, scrape, source_url)


def _merge_coral_comments_if_available(scrape: ScrapeResult) -> ScrapeResult:
    html_text = scrape.html
    if not html_text or not html_text.strip():
        return scrape
    signal = detect_coral(html_text)
    if signal is None or not signal.supports_graphql:
        return scrape
    try:
        comments = run_sync(fetch_coral_comments(signal.graphql_origin, signal.story_url))
    except (CoralFetchError, CoralUnsupportedError):
        return scrape
    return merge_coral_into_scrape(scrape, comments.comments_markdown)


def _extract_coral_utterances(
    scrape: ScrapeResult,
    source_url: str,
    *,
    post_id: str | None,
) -> list[Utterance]:
    root = _parse_html(scrape.html)
    if root is not None:
        marker_utterances = _extract_coral_marker_utterances(root, source_url, post_id=post_id)
        if marker_utterances:
            return marker_utterances
    return _extract_coral_markdown_utterances(scrape.markdown, source_url, post_id=post_id)


def _extract_coral_marker_utterances(
    root: HtmlElement,
    source_url: str,
    *,
    post_id: str | None,
) -> list[Utterance]:
    markers = root.xpath("//*[@data-coral-comments]")
    if not markers:
        return []
    utterances: list[Utterance] = []
    for marker in markers:
        if not isinstance(marker, HtmlElement):
            continue
        top_level_comments = [
            article
            for article in marker.xpath(
                './/article[contains(concat(" ", normalize-space(@class), " "), " comment ")]'
            )
            if isinstance(article, HtmlElement)
            and not article.xpath(
                'ancestor::article[contains(concat(" ", normalize-space(@class), " "), " comment ")]'
            )
        ]
        for comment in top_level_comments:
            utterances.extend(_flatten_coral_marker_comment_tree(comment, post_id, source_url))
    return utterances


def _flatten_coral_marker_comment_tree(
    comment: HtmlElement,
    post_id: str | None,
    source_url: str,
) -> list[Utterance]:
    kind = "reply" if comment.get("data-parent-id") else "comment"
    utterance_id = _stable_utterance_id(comment, kind)
    parent_id = comment.get("data-parent-id") or post_id
    fragment = _element_fragment(comment, nested_container_xpaths=("./article",))
    utterances = [
        Utterance(
            utterance_id=utterance_id,
            kind=kind,  # pyright: ignore[reportArgumentType]
            text=_coral_marker_body_text(comment),
            author=_coral_marker_author(comment),
            parent_id=parent_id,
            mentioned_urls=_extract_urls(fragment, source_url),
            mentioned_images=extract_image_urls(fragment, source_url),
            mentioned_videos=extract_video_urls(fragment, source_url),
        )
    ]
    for nested in comment.xpath("./article"):
        if isinstance(nested, HtmlElement):
            utterances.extend(_flatten_coral_marker_comment_tree(nested, utterance_id, source_url))
    return utterances


def _coral_marker_author(comment: HtmlElement) -> str | None:
    author = _clean_text(comment.xpath("string(./header[1])"))
    return author or None


def _coral_marker_body_text(comment: HtmlElement) -> str:
    texts = _collect_texts(comment, ("./p", "./div/p"))
    if texts:
        return "\n".join(texts)
    clone = _pruned_clone(comment, nested_container_xpaths=("./article",))
    for header in clone.xpath("./header"):
        parent = header.getparent()
        if parent is not None:
            parent.remove(header)
    return _clean_text(clone.text_content())


def _extract_coral_markdown_utterances(
    markdown: str | None,
    source_url: str,
    *,
    post_id: str | None,
) -> list[Utterance]:
    if not markdown or "## Comments" not in markdown:
        return []
    comment_lines: list[str] = []
    in_comments = False
    for line in markdown.splitlines():
        if not in_comments:
            if line.strip() == "## Comments":
                in_comments = True
            continue
        if line.startswith("## ") and line.strip() != "## Comments":
            break
        comment_lines.append(unescape(line.rstrip("\n")))
    if not comment_lines:
        return []

    utterances: list[Utterance] = []
    i = 0
    while i < len(comment_lines):
        match = _CORAL_HEADER_RE.match(comment_lines[i])
        if match is None:
            i += 1
            continue
        indent = match.group("indent")
        body_lines: list[str] = []
        i += 1
        while i < len(comment_lines):
            next_line = comment_lines[i]
            if _CORAL_HEADER_RE.match(next_line):
                break
            if next_line.startswith(f"{indent}  "):
                body_lines.append(next_line[len(indent) + 2 :])
            elif next_line.strip():
                body_lines.append(next_line.strip())
            i += 1
        author = unquote(match.group("author"))
        raw_parent = match.group("parent")
        utterances.append(
            Utterance(
                utterance_id=match.group("id"),
                kind="reply" if raw_parent != "null" else "comment",
                text=_clean_text("\n".join(body_lines)),
                author=None if author == "anonymous" else author,
                parent_id=post_id if raw_parent == "null" else raw_parent,
                mentioned_urls=_extract_urls("\n".join(body_lines), source_url),
                mentioned_images=[],
                mentioned_videos=[],
            )
        )
    return utterances


def _extract_blog_post(
    root: HtmlElement,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    utterances: list[Utterance] = []
    post = _first(root, "//*[@data-role='post'][1]")
    if post is None:
        post = _first(root, "//article[1]")
    if post is not None:
        utterances.append(
            _build_utterance(
                post,
                kind="post",
                parent_id=None,
                source_url=source_url,
                text_hint=_body_text(post),
            )
        )

    comments_root = _first(root, "//section[@data-comments]")
    if comments_root is None:
        return utterances

    post_id = utterances[0].utterance_id if utterances else None
    for comment in comments_root.xpath("./article"):
        utterances.extend(_flatten_blog_comment_tree(comment, post_id, source_url))
    return utterances


def _flatten_blog_comment_tree(
    comment: HtmlElement,
    post_id: str | None,
    source_url: str,
) -> list[Utterance]:
    kind = "reply" if comment.get("data-parent-id") else "comment"
    utterance_id = _stable_utterance_id(comment, kind)
    parent_id = comment.get("data-parent-id") or post_id
    utterances = [
        _build_utterance(
            comment,
            kind=kind,
            parent_id=parent_id,
            source_url=source_url,
            text_hint=_comment_text(comment, nested_container_xpaths=("./article",)),
            utterance_id=utterance_id,
            nested_container_xpaths=("./article",),
        )
    ]
    for nested in comment.xpath("./article"):
        utterances.extend(_flatten_blog_comment_tree(nested, utterance_id, source_url))
    return utterances


def _extract_forum_thread(
    root: HtmlElement,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    utterances: list[Utterance] = []
    post = _first(root, "//*[@data-role='post'][1]")
    if post is None:
        post = _first(root, "//article[1]")
    if post is None:
        return utterances

    post_utterance = _build_utterance(
        post,
        kind="post",
        parent_id=None,
        source_url=source_url,
        text_hint=_body_text(post),
    )
    utterances.append(post_utterance)

    replies = root.xpath("//*[@data-reply-id]")
    if not replies:
        post_parent = post.getparent()
        if post_parent is not None:
            replies = [
                candidate
                for candidate in post_parent.xpath("./*")
                if isinstance(candidate, HtmlElement)
                and candidate is not post
                and not _is_coral_scaffold_element(candidate)
                and _clean_text(candidate.text_content())
            ]
    for reply in replies:
        utterances.append(
            _build_utterance(
                reply,
                kind="reply",
                parent_id=post_utterance.utterance_id,
                source_url=source_url,
                text_hint=_comment_text(reply),
            )
        )
    return utterances


def _extract_hierarchical_thread(
    root: HtmlElement,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    utterances: list[Utterance] = []
    post = _first(root, "//*[@data-role='post'][1]")
    if post is None:
        post = _first(root, "//article[1]")
    if post is not None:
        post_utterance = _build_utterance(
            post,
            kind="post",
            parent_id=None,
            source_url=source_url,
            text_hint=_body_text(post),
        )
        utterances.append(post_utterance)
        post_id = post_utterance.utterance_id
    else:
        post_id = None

    nodes = root.xpath("//*[@data-node-id]")
    if nodes:
        for node in nodes:
            utterances.append(
                _build_utterance(
                    node,
                    kind="reply",
                    parent_id=node.get("data-parent-id"),
                    source_url=source_url,
                    text_hint=_comment_text(node),
                )
            )
        return utterances

    for node in root.xpath("//li[not(ancestor::li) and not(ancestor::*[@data-role='post'])]"):
        utterances.extend(
            _flatten_hierarchical_node_tree(
                node,
                parent_id=post_id,
                source_url=source_url,
            )
        )
    return utterances


def _flatten_hierarchical_node_tree(
    node: HtmlElement,
    parent_id: str | None,
    source_url: str,
) -> list[Utterance]:
    utterance_id = _stable_utterance_id(node, "reply")
    utterances = [
        _build_utterance(
            node,
            kind="reply",
            parent_id=parent_id,
            source_url=source_url,
            text_hint=_comment_text(node, nested_container_xpaths=("./ul/li", "./ol/li")),
            utterance_id=utterance_id,
            nested_container_xpaths=("./ul/li", "./ol/li"),
        )
    ]
    for child in node.xpath("./ul/li | ./ol/li"):
        utterances.extend(
            _flatten_hierarchical_node_tree(
                child,
                parent_id=utterance_id,
                source_url=source_url,
            )
        )
    return utterances


def _extract_blog_index(root: HtmlElement, source_url: str) -> list[Utterance]:
    utterances: list[Utterance] = []
    for entry in root.xpath("//*[@data-entry-id]"):
        texts = _collect_texts(entry, ("./h1", "./h2", "./h3", "./p"))
        if not texts:
            continue
        utterances.append(
            _build_utterance(
                entry,
                kind="post",
                parent_id=None,
                source_url=source_url,
                text_hint="\n".join(texts),
            )
        )
    return utterances


def _extract_article(
    root: HtmlElement,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    article = _first(root, "//article[1]")
    if article is None:
        return []
    return [
        _build_utterance(
            article,
            kind="post",
            parent_id=None,
            source_url=source_url,
            text_hint=_body_text(article) or _markdown_text(scrape.markdown),
        )
    ]


def _extract_other(
    root: HtmlElement,
    scrape: ScrapeResult,
    source_url: str,
) -> list[Utterance]:
    text = _markdown_text(scrape.markdown)
    if not text:
        text = _clean_text(root.text_content())
    if not text:
        return []
    return [
        Utterance(
            utterance_id="post-0",
            kind="post",
            text=text,
            author=None,
            parent_id=None,
            mentioned_urls=_extract_urls(scrape.html or "", source_url),
            mentioned_images=extract_image_urls(scrape.html or scrape.markdown, source_url),
            mentioned_videos=extract_video_urls(scrape.html or scrape.markdown, source_url),
        )
    ]


def _fallback_utterance(scrape: ScrapeResult, source_url: str) -> Utterance:
    text = _markdown_text(scrape.markdown) or _clean_text(scrape.html or "") or source_url
    content = scrape.html or scrape.markdown or ""
    return Utterance(
        utterance_id="post-0",
        kind="post",
        text=text,
        author=None,
        parent_id=None,
        mentioned_urls=_extract_urls(content, source_url),
        mentioned_images=extract_image_urls(content, source_url),
        mentioned_videos=extract_video_urls(content, source_url),
    )


def _build_utterance(
    element: HtmlElement,
    *,
    kind: str,
    parent_id: str | None,
    source_url: str,
    text_hint: str,
    utterance_id: str | None = None,
    nested_container_xpaths: Iterable[str] = (),
) -> Utterance:
    fragment = _element_fragment(element, nested_container_xpaths=nested_container_xpaths)
    return Utterance(
        utterance_id=utterance_id or _stable_utterance_id(element, kind),
        kind=kind,  # pyright: ignore[reportArgumentType]
        text=text_hint,
        author=_author_text(element),
        parent_id=parent_id,
        mentioned_urls=_extract_urls(fragment, source_url),
        mentioned_images=extract_image_urls(fragment, source_url),
        mentioned_videos=extract_video_urls(fragment, source_url),
    )


def _element_id(element: HtmlElement) -> str | None:
    for attr_name in (
        "data-utterance-id",
        "data-comment-id",
        "data-reply-id",
        "data-node-id",
        "data-entry-id",
        "id",
    ):
        value = element.get(attr_name)
        if value:
            return value
    return None


def _stable_utterance_id(element: HtmlElement, kind: str) -> str:
    explicit_id = _element_id(element)
    if explicit_id:
        return explicit_id
    path = element.getroottree().getpath(element)
    digest = sha1(path.encode("utf-8")).hexdigest()[:12]
    return f"{kind}-{digest}"


def _author_text(element: HtmlElement) -> str | None:
    author = element.xpath("string(.//*[@data-author][1])")
    cleaned = _clean_text(author)
    return cleaned or None


def _body_text(element: HtmlElement) -> str:
    texts = _collect_texts(element, (".//*[@data-body]//p", "./p[not(@data-author)]"))
    if texts:
        return "\n".join(texts)
    return _comment_text(element)


def _comment_text(
    element: HtmlElement,
    *,
    nested_container_xpaths: Iterable[str] = (),
) -> str:
    texts = _collect_texts(element, ("./p[not(@data-author)]", "./div/p[not(@data-author)]"))
    if texts:
        return "\n".join(texts)
    clone = _pruned_clone(element, nested_container_xpaths=nested_container_xpaths)
    for author in clone.xpath(".//*[@data-author]"):
        parent = author.getparent()
        if parent is not None:
            parent.remove(author)
    return _clean_text(clone.text_content())


def _collect_texts(element: HtmlElement, xpaths: Iterable[str]) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for xpath in xpaths:
        for node in element.xpath(xpath):
            text = _clean_text(node.text_content())
            if text and text not in seen:
                seen.add(text)
                texts.append(text)
    return texts


def _is_coral_scaffold_element(element: HtmlElement) -> bool:
    if element.tag.lower() == "ps-comments":
        return True
    if element.get("data-coral-comments") is not None:
        return True
    element_id = (element.get("id") or "").lower()
    if element_id in {"coral_talk_stream", "coral_thread", "coral-thread"}:
        return True
    class_value = (element.get("class") or "").lower()
    return "coral" in class_value


def _extract_urls(content: str, source_url: str) -> list[str]:
    urls: list[str] = []
    for match in _URL_TAG_RE.finditer(content):
        normalized = normalize_public_url(match.group("url"), source_url)
        if normalized is not None and normalized not in urls:
            urls.append(normalized)
    return urls


def _element_fragment(
    element: HtmlElement,
    *,
    nested_container_xpaths: Iterable[str] = (),
) -> str:
    return lxml_html.tostring(
        _pruned_clone(element, nested_container_xpaths=nested_container_xpaths),
        encoding="unicode",
    )


def _pruned_clone(
    element: HtmlElement,
    *,
    nested_container_xpaths: Iterable[str] = (),
) -> HtmlElement:
    clone = lxml_html.fromstring(lxml_html.tostring(element, encoding="unicode"))
    selectors = (_UTTERANCE_CONTAINER_XPATH, *nested_container_xpaths)
    for xpath in selectors:
        for nested in clone.xpath(xpath):
            if nested is clone:
                continue
            parent = nested.getparent()
            if parent is not None:
                parent.remove(nested)
    return clone


def _markdown_text(markdown: str | None) -> str:
    if not markdown:
        return ""
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("!"):
            continue
        lines.append(re.sub(r"^#+\s*", "", line))
    return _clean_text("\n".join(lines))


def _clean_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _first(element: HtmlElement, xpath: str) -> HtmlElement | None:
    matches = element.xpath(xpath)
    if not matches:
        return None
    first = matches[0]
    return first if isinstance(first, HtmlElement) else None
