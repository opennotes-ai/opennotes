"""Async Coral GraphQL client used by the tier-2 extractor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .render import render_to_markdown

CORAL_GRAPHQL_QUERY = """
query CoralStoryComments($url: String!, $first: Int = 50) {
  stream(url: $url) {
    comments(first: $first, orderBy: CREATED_AT_ASC) {
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


class _CoralCommentsConnection(BaseModel):
    edges: list[_CoralCommentEdge]


class _CoralStream(BaseModel):
    comments: _CoralCommentsConnection


class _CoralPayload(BaseModel):
    stream: _CoralStream


class _GraphqlResponse(BaseModel):
    data: _CoralPayload


def _to_nodes(payload: dict[str, Any]) -> list[CoralCommentNode]:
    parsed = _GraphqlResponse.model_validate(payload)
    return [edge.node.as_public() for edge in parsed.data.stream.comments.edges]


def _safe_request_body(url: str) -> dict[str, Any]:
    return {
        "query": CORAL_GRAPHQL_QUERY,
        "variables": {
            "url": url,
            "first": 50,
        },
    }


async def fetch_coral_comments(
    graphql_origin: str,
    story_url: str,
    *,
    timeout: float = 10.0,
    max_attempts: int = 2,
) -> CoralComments:
    """Fetch Coral comments from ``/api/graphql`` and render markdown.

    The client is intentionally defensive: transient transport conditions are
    retried while 4xx/GraphQL parse/schema errors are terminal.
    """

    endpoint = graphql_origin.rstrip("/") + "/api/graphql"
    body = _safe_request_body(story_url)

    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
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
                nodes = _to_nodes(payload)
            except ValidationError as exc:
                raise CoralUnsupportedError("coral graphql payload schema mismatch") from exc

            return CoralComments(
                comments_markdown=render_to_markdown(nodes),
                raw_count=len(nodes),
                fetched_at=datetime.now(UTC),
            )

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
