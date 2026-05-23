from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.url_content_scan.viafoura.api import (
    ViafouraFetchError,
    ViafouraUnsupportedError,
    fetch_viafoura_comments,
)
from src.url_content_scan.viafoura.detector import ViafouraSignal

pytestmark = pytest.mark.unit

STORY_URL = "https://www.example.com/2026/05/article"

_SIGNAL = ViafouraSignal(
    container_id="ctr-001",
    site_domain="example.com",
    embed_origin="https://cdn.viafoura.net",
)

_BOOTSTRAP_PAYLOAD: dict[str, Any] = {
    "result": {
        "settings": {"site_uuid": "site-uuid-1234"},
        "sectionTree": {"uuid": "section-uuid-5678"},
    }
}

_CONTAINER_PAYLOAD: dict[str, Any] = {
    "container_id": "ctr-001",
    "content_container_uuid": "content-uuid-9999",
    "total_visible_content": 2,
}


def _make_comment(
    *,
    content_uuid: str,
    content: str,
    date_created: int,
    actor_name: str | None = "alice",
    actor_uuid: str | None = None,
    parent_uuid: str | None = None,
    state: str = "visible",
) -> dict[str, Any]:
    actor: dict[str, Any] | None = None
    if actor_name is not None:
        actor = {"name": actor_name, "username": None}
    return {
        "content_uuid": content_uuid,
        "content": content,
        "date_created": date_created,
        "state": state,
        "actor": actor,
        "actor_uuid": actor_uuid,
        "parent_uuid": parent_uuid,
    }


def _comments_payload(
    contents: list[dict[str, Any]],
    *,
    more_available: bool = False,
) -> dict[str, Any]:
    return {"more_available": more_available, "contents": contents}


def _make_httpx_stub(responses: list[dict[str, Any]]) -> Any:
    call_index = {"i": 0}

    async def _mock_request(
        method: str, url: str, *, headers: Any = None, json: Any = None
    ) -> httpx.Response:
        idx = call_index["i"]
        call_index["i"] += 1
        if idx >= len(responses):
            raise AssertionError(f"Unexpected request {idx} to {url}")
        payload = responses[idx]
        request = httpx.Request(method, url)
        return httpx.Response(200, json=payload, request=request)

    mock_client = MagicMock()
    mock_client.request = _mock_request
    return mock_client


async def test_fetch_viafoura_comments_returns_nodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ts = int(datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    comments = _comments_payload(
        [
            _make_comment(content_uuid="c1", content="<p>Hello world</p>", date_created=ts),
            _make_comment(
                content_uuid="c2",
                content="<p>Reply here</p>",
                date_created=ts + 5000,
                actor_name="bob",
                parent_uuid="content-uuid-9999",
            ),
        ]
    )
    client = _make_httpx_stub([_BOOTSTRAP_PAYLOAD, _CONTAINER_PAYLOAD, comments])

    result = await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=client)

    assert result.raw_count == 2
    assert isinstance(result.fetched_at, datetime)
    assert "[c1] author=alice" in result.comments_markdown
    assert "Hello world" in result.comments_markdown
    assert result.nodes[0].author_username == "alice"
    assert result.nodes[1].author_username == "bob"
    assert result.nodes[1].parent_id is None


async def test_fetch_viafoura_comments_uses_actor_uuid_as_pseudonym(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ts = int(datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    comments = _comments_payload(
        [
            _make_comment(
                content_uuid="c-anon",
                content="<p>Anonymous comment</p>",
                date_created=ts,
                actor_name=None,
                actor_uuid="550e8400-e29b-41d4-a716-446655440000",
            )
        ]
    )
    client = _make_httpx_stub([_BOOTSTRAP_PAYLOAD, _CONTAINER_PAYLOAD, comments])

    result = await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=client)

    assert result.raw_count == 1
    node = result.nodes[0]
    assert node.author_username == "user-550e8400"
    assert node.actor_uuid == "550e8400-e29b-41d4-a716-446655440000"


async def test_fetch_viafoura_comments_raises_on_missing_container_id() -> None:
    signal = ViafouraSignal(container_id=None)
    mock_client = MagicMock()
    with pytest.raises(ViafouraUnsupportedError, match="missing container_id"):
        await fetch_viafoura_comments(signal, STORY_URL, client=mock_client)


async def test_fetch_viafoura_comments_raises_on_unsafe_url() -> None:
    mock_client = MagicMock()
    with pytest.raises(ViafouraUnsupportedError, match="unsafe story URL"):
        await fetch_viafoura_comments(_SIGNAL, "javascript:alert(1)", client=mock_client)


async def test_fetch_viafoura_comments_skips_non_visible_content() -> None:
    ts = int(datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    comments = _comments_payload(
        [
            _make_comment(content_uuid="c1", content="<p>Visible</p>", date_created=ts),
            _make_comment(
                content_uuid="c2",
                content="<p>Removed</p>",
                date_created=ts + 1000,
                state="moderated",
            ),
        ]
    )
    client = _make_httpx_stub([_BOOTSTRAP_PAYLOAD, _CONTAINER_PAYLOAD, comments])

    result = await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=client)

    assert result.raw_count == 1
    assert result.nodes[0].id == "c1"


async def test_fetch_viafoura_comments_appends_truncation_marker() -> None:
    ts = int(datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    comments = _comments_payload(
        [_make_comment(content_uuid="c1", content="<p>Text</p>", date_created=ts)],
        more_available=True,
    )
    client = _make_httpx_stub([_BOOTSTRAP_PAYLOAD, _CONTAINER_PAYLOAD, comments])

    result = await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=client)

    assert result.more_available is True
    assert "[comments truncated]" in result.comments_markdown


async def test_fetch_viafoura_comments_raises_on_bootstrap_schema_mismatch() -> None:
    bad_payload = {"result": "not-an-object"}
    client = _make_httpx_stub([bad_payload])
    with pytest.raises(ViafouraUnsupportedError, match="schema mismatch"):
        await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=client)


async def test_fetch_viafoura_comments_raises_on_transport_error() -> None:
    async def _fail_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    mock_client = MagicMock()
    mock_client.request = _fail_request

    with pytest.raises(ViafouraFetchError):
        await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=mock_client, max_attempts=1)


async def test_fetch_viafoura_comments_retries_on_server_error() -> None:
    ts = int(datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    call_count = {"n": 0}

    async def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        call_count["n"] += 1
        request_obj = httpx.Request(method, url)
        if "bootstrap" in url and call_count["n"] == 1:
            return httpx.Response(503, text="", request=request_obj)
        if "bootstrap" in url:
            return httpx.Response(200, json=_BOOTSTRAP_PAYLOAD, request=request_obj)
        if "contentcontainer" in url:
            return httpx.Response(200, json=_CONTAINER_PAYLOAD, request=request_obj)
        payload = _comments_payload(
            [_make_comment(content_uuid="c1", content="<p>Ok</p>", date_created=ts)]
        )
        return httpx.Response(200, json=payload, request=request_obj)

    mock_client = MagicMock()
    mock_client.request = _request

    result = await fetch_viafoura_comments(_SIGNAL, STORY_URL, client=mock_client, max_attempts=2)
    assert result.raw_count == 1
