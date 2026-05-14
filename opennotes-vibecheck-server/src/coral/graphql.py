"""Async Coral GraphQL client used by the tier-2 extractor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.utils.url_security import InvalidURL, validate_public_http_url

from .render import render_to_markdown

CORAL_GRAPHQL_QUERY = """
query CoralStoryComments($url: String!, $first: Int = 50, $after: Cursor) {
  stream(url: $url) {
    comments(first: $first, after: $after, orderBy: CREATED_AT_ASC) {
      pageInfo {
        endCursor
        hasNextPage
      }
      edges {
        node {
          id
          body
          createdAt
          author { username }
          parent { id }
        }
      }
    }
  }
}
""".strip()

_RETRY_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_PAGE_SIZE = 50
# Bound Coral GraphQL work for very large threads while returning partial text.
_DEFAULT_MAX_COMMENTS = 300
_TRUNCATION_MARKER = "[comments truncated]"


class CoralFetchError(Exception):
    """Transient network/transport-level failure (retry/escalate)."""


class CoralUnsupportedError(Exception):
    """Terminal failure: unsupported path, schema mismatch, or bad payload."""


class CoralCommentNode(BaseModel):
    """Normalized comment node for renderer consumption."""

    id: str
    body: str
    author_username: str | None
    parent_id: str | None
    created_at: datetime


class CoralComments(BaseModel):
    """Output contract for `/api/graphql` comment fetches."""

    comments_markdown: str
    nodes: list[CoralCommentNode] = Field(default_factory=list)
    raw_count: int
    fetched_at: datetime
    model_config = ConfigDict(extra="ignore")


class _CoralAuthor(BaseModel):
    username: str | None = None


class _CoralParent(BaseModel):
    id: str | None = None


class _CoralCommentNode(BaseModel):
    id: str
    body: str
    created_at: datetime = Field(validation_alias="createdAt")
    author: _CoralAuthor | None
    parent: _CoralParent | None
    model_config = ConfigDict(populate_by_name=True)

    def as_public(self) -> CoralCommentNode:
        return CoralCommentNode(
            id=self.id,
            body=self.body,
            author_username=self.author.username if self.author else None,
            parent_id=self.parent.id if self.parent else None,
            created_at=self.created_at,
        )


class _CoralCommentEdge(BaseModel):
    node: _CoralCommentNode


class _CoralPageInfo(BaseModel):
    end_cursor: str | None = Field(default=None, validation_alias="endCursor")
    has_next_page: bool = Field(validation_alias="hasNextPage")
    model_config = ConfigDict(populate_by_name=True)


class _CoralCommentsConnection(BaseModel):
    page_info: _CoralPageInfo = Field(validation_alias="pageInfo")
    edges: list[_CoralCommentEdge]
    model_config = ConfigDict(populate_by_name=True)


class _CoralStream(BaseModel):
    comments: _CoralCommentsConnection


class _CoralPayload(BaseModel):
    stream: _CoralStream


class _GraphqlResponse(BaseModel):
    data: _CoralPayload


def _to_page(payload: dict[str, Any]) -> tuple[list[CoralCommentNode], _CoralPageInfo]:
    parsed = _GraphqlResponse.model_validate(payload)
    comments = parsed.data.stream.comments
    return [edge.node.as_public() for edge in comments.edges], comments.page_info


def _safe_request_body(
    url: str,
    *,
    first: int = _DEFAULT_PAGE_SIZE,
    after: str | None = None,
) -> dict[str, Any]:
    return {
        "query": CORAL_GRAPHQL_QUERY,
        "variables": {
            "url": url,
            "first": first,
            "after": after,
        },
    }


def _with_truncation_marker(comments_markdown: str) -> str:
    return f"{comments_markdown.rstrip()}\n{_TRUNCATION_MARKER}"


async def _fetch_coral_page(
    client: httpx.AsyncClient,
    endpoint: str,
    story_url: str,
    *,
    first: int,
    after: str | None,
    max_attempts: int,
) -> tuple[list[CoralCommentNode], _CoralPageInfo]:
    body = _safe_request_body(story_url, first=first, after=after)
    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            response = await client.post(endpoint, json=body)

            if response.status_code in _RETRY_STATUS:
                raise CoralFetchError(
                    f"coral graphql retryable response: {response.status_code}"
                )

            if response.status_code >= 400:
                raise CoralUnsupportedError(
                    f"coral graphql unsupported status code: {response.status_code}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise CoralUnsupportedError("coral graphql response was not valid JSON") from exc

            if not isinstance(payload, dict):
                raise CoralUnsupportedError("coral graphql response has non-object payload")
            if payload.get("errors"):
                raise CoralUnsupportedError("coral graphql returned GraphQL errors")

            try:
                return _to_page(payload)
            except ValidationError as exc:
                raise CoralUnsupportedError("coral graphql payload schema mismatch") from exc

        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            continue
        except CoralFetchError:
            last_error = None
            continue
        except CoralUnsupportedError:
            raise

    if last_error is not None:
        raise CoralFetchError(f"coral graphql failed after retry budget: {last_error!s}")

    raise CoralFetchError("coral graphql exhausted retry attempts")


async def fetch_coral_comments(
    graphql_origin: str,
    story_url: str,
    *,
    timeout: float = 10.0,
    max_attempts: int = 2,
    page_size: int = _DEFAULT_PAGE_SIZE,
    max_comments: int = _DEFAULT_MAX_COMMENTS,
) -> CoralComments:
    """Fetch Coral comments from ``/api/graphql`` and render markdown.

    The client is intentionally defensive: transient transport conditions are
    retried while 4xx/GraphQL parse/schema errors are terminal.
    """
    if page_size < 1:
        raise ValueError("page_size must be at least 1")
    if max_comments < 1:
        raise ValueError("max_comments must be at least 1")

    raw_endpoint = graphql_origin.rstrip("/") + "/api/graphql"
    try:
        endpoint = validate_public_http_url(raw_endpoint)
    except InvalidURL as exc:
        raise CoralUnsupportedError(
            f"coral graphql unsafe endpoint: {exc.reason}"
        ) from exc

    nodes: list[CoralCommentNode] = []
    after: str | None = None
    truncated = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            remaining = max_comments - len(nodes)
            if remaining <= 0:
                truncated = True
                break

            page_nodes, page_info = await _fetch_coral_page(
                client,
                endpoint,
                story_url,
                first=min(page_size, remaining),
                after=after,
                max_attempts=max_attempts,
            )

            if len(page_nodes) > remaining:
                nodes.extend(page_nodes[:remaining])
                truncated = True
                break

            nodes.extend(page_nodes)

            if not page_info.has_next_page:
                break

            if len(nodes) >= max_comments:
                truncated = True
                break

            if page_info.end_cursor is None:
                raise CoralUnsupportedError("coral graphql pagination cursor missing")

            after = page_info.end_cursor

    comments_markdown = render_to_markdown(nodes)
    if truncated:
        comments_markdown = _with_truncation_marker(comments_markdown)

    return CoralComments(
        comments_markdown=comments_markdown,
        nodes=nodes,
        raw_count=len(nodes),
        fetched_at=datetime.now(UTC),
    )
