"""Async Viafoura public comments API client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.utils.url_security import InvalidURL, validate_public_http_url

from .detector import ViafouraSignal
from .render import render_to_markdown

_BOOTSTRAP_API_ORIGIN = "https://api.viafoura.co"
_COMMENTS_API_ORIGIN = "https://livecomments.viafoura.co"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_LIMIT = 50
_DEFAULT_REPLY_LIMIT = 5
_DEFAULT_MAX_COMMENTS = 300
_TRUNCATION_MARKER = "[comments truncated]"


class ViafouraFetchError(Exception):
    """Transient network/transport-level failure."""


class ViafouraUnsupportedError(Exception):
    """Terminal failure: unsupported path, schema mismatch, or bad payload."""


class ViafouraCommentNode(BaseModel):
    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: datetime


class ViafouraComments(BaseModel):
    comments_markdown: str
    nodes: list[ViafouraCommentNode] = Field(default_factory=list)
    raw_count: int
    fetched_at: datetime
    more_available: bool
    model_config = ConfigDict(extra="ignore")


class _BootstrapSettings(BaseModel):
    site_uuid: str | None = None


class _BootstrapSectionTree(BaseModel):
    uuid: str | None = None


class _BootstrapResult(BaseModel):
    settings: _BootstrapSettings | None = None
    section_tree: _BootstrapSectionTree | None = Field(
        default=None,
        validation_alias="sectionTree",
    )
    model_config = ConfigDict(populate_by_name=True)


class _BootstrapPayload(BaseModel):
    result: _BootstrapResult


class _ContainerPayload(BaseModel):
    container_id: str
    content_container_uuid: str
    total_visible_content: int | None = None


class _ViafouraActor(BaseModel):
    name: str | None = None
    username: str | None = None


class _ViafouraContent(BaseModel):
    content_uuid: str
    parent_uuid: str | None = None
    content: str
    date_created: int
    state: str | None = None
    actor: _ViafouraActor | None = None
    author: _ViafouraActor | None = None

    def as_public(self, *, container_uuid: str) -> ViafouraCommentNode | None:
        if self.state is not None and self.state.lower() != "visible":
            return None
        author = self.actor or self.author
        parent_id = self.parent_uuid if self.parent_uuid != container_uuid else None
        return ViafouraCommentNode(
            id=self.content_uuid,
            body=self.content,
            author_username=(author.name or author.username) if author else None,
            parent_id=parent_id,
            created_at=datetime.fromtimestamp(self.date_created / 1000, tz=UTC),
        )


class _CommentsPayload(BaseModel):
    more_available: bool = False
    contents: list[_ViafouraContent]


def _domain_for(story_url: str, signal: ViafouraSignal) -> str:
    if signal.site_domain:
        return signal.site_domain
    parsed = urlparse(story_url)
    host = parsed.hostname or ""
    if host.startswith("www."):
        return host[4:]
    return host


def _headers(story_url: str) -> dict[str, str]:
    parsed = urlparse(story_url)
    origin = f"{parsed.scheme}://{parsed.hostname}"
    return {"Origin": origin, "Referer": story_url}


def _bootstrap_url(domain: str) -> str:
    return f"{_BOOTSTRAP_API_ORIGIN}/v2/{domain}/bootstrap/v2?session=false"


def _container_url(section_uuid: str, container_id: str) -> str:
    query = urlencode({"container_id": container_id})
    return (
        f"{_COMMENTS_API_ORIGIN}/v4/livecomments/{section_uuid}/contentcontainer/id"
        f"?{query}"
    )


def _comments_url(
    section_uuid: str,
    content_container_uuid: str,
    *,
    limit: int,
    reply_limit: int,
    sorted_by: str,
) -> str:
    query = urlencode(
        {
            "limit": limit,
            "reply_limit": reply_limit,
            "sorted_by": sorted_by,
        }
    )
    return (
        f"{_COMMENTS_API_ORIGIN}/v4/livecomments/{section_uuid}/"
        f"{content_container_uuid}/comments?{query}"
    )


async def _request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    max_attempts: int,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(max_attempts):
        try:
            response = await client.request(method, url, headers=headers, json=json_body)
            if response.status_code in _RETRY_STATUS:
                raise ViafouraFetchError(
                    f"viafoura retryable response: {response.status_code}"
                )
            if response.status_code >= 400:
                raise ViafouraUnsupportedError(
                    f"viafoura unsupported status code: {response.status_code}"
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise ViafouraUnsupportedError("viafoura response has non-object payload")
            return payload
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            continue
        except ViafouraFetchError:
            last_error = None
            continue
        except ValueError as exc:
            raise ViafouraUnsupportedError("viafoura response was not valid JSON") from exc

    if last_error is not None:
        raise ViafouraFetchError(f"viafoura failed after retry budget: {last_error!s}")
    raise ViafouraFetchError("viafoura exhausted retry attempts")


async def fetch_viafoura_comments(
    signal: ViafouraSignal,
    story_url: str,
    *,
    client: httpx.AsyncClient,
    limit: int = _DEFAULT_LIMIT,
    reply_limit: int = _DEFAULT_REPLY_LIMIT,
    sorted_by: str = "newest",
    max_attempts: int = 2,
    max_comments: int = _DEFAULT_MAX_COMMENTS,
) -> ViafouraComments:
    """Fetch Viafoura comments from the public bootstrap/container/comments path."""
    try:
        safe_story_url = validate_public_http_url(story_url)
    except InvalidURL as exc:
        raise ViafouraUnsupportedError("unsafe story URL") from exc
    if not signal.container_id:
        raise ViafouraUnsupportedError("viafoura signal missing container_id")

    domain = _domain_for(safe_story_url, signal)
    headers = _headers(safe_story_url)
    bootstrap_payload = await _request_json(
        client,
        "POST",
        _bootstrap_url(domain),
        headers=headers,
        json_body={"section": "", "section_tree": "", "session": "false"},
        max_attempts=max_attempts,
    )
    try:
        bootstrap = _BootstrapPayload.model_validate(bootstrap_payload)
    except ValidationError as exc:
        raise ViafouraUnsupportedError("viafoura bootstrap schema mismatch") from exc

    section_uuid = (
        bootstrap.result.settings.site_uuid if bootstrap.result.settings else None
    ) or (
        bootstrap.result.section_tree.uuid
        if bootstrap.result.section_tree
        else None
    )
    if not section_uuid:
        raise ViafouraUnsupportedError("viafoura bootstrap missing section uuid")

    container_payload = await _request_json(
        client,
        "GET",
        _container_url(section_uuid, signal.container_id),
        headers=headers,
        max_attempts=max_attempts,
    )
    try:
        container = _ContainerPayload.model_validate(container_payload)
    except ValidationError as exc:
        raise ViafouraUnsupportedError("viafoura container schema mismatch") from exc

    comments_payload = await _request_json(
        client,
        "GET",
        _comments_url(
            section_uuid,
            container.content_container_uuid,
            limit=limit,
            reply_limit=reply_limit,
            sorted_by=sorted_by,
        ),
        headers=headers,
        max_attempts=max_attempts,
    )
    try:
        parsed_comments = _CommentsPayload.model_validate(comments_payload)
    except ValidationError as exc:
        raise ViafouraUnsupportedError("viafoura comments schema mismatch") from exc

    nodes = [
        node
        for item in parsed_comments.contents[:max_comments]
        if (node := item.as_public(container_uuid=container.content_container_uuid))
        is not None
    ]
    markdown = render_to_markdown(nodes)
    if parsed_comments.more_available:
        markdown = f"{markdown.rstrip()}\n{_TRUNCATION_MARKER}"

    return ViafouraComments(
        comments_markdown=markdown,
        nodes=nodes,
        raw_count=len(nodes),
        fetched_at=datetime.now(UTC),
        more_available=parsed_comments.more_available,
    )


__all__ = [
    "ViafouraCommentNode",
    "ViafouraComments",
    "ViafouraFetchError",
    "ViafouraUnsupportedError",
    "fetch_viafoura_comments",
]
