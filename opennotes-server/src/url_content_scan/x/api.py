from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

_API_BASE = "https://api.x.com"
_TWEET_FIELDS = "created_at,conversation_id,in_reply_to_user_id,referenced_tweets"
_USER_FIELDS = "username,name"


class XTweet(BaseModel):
    id: str
    text: str
    author_id: str
    author_handle: str
    author_name: str
    created_at: datetime
    in_reply_to_status_id: str | None
    model_config = ConfigDict(frozen=True)


class XConversation(BaseModel):
    root: XTweet
    replies: list[XTweet]
    raw_count: int
    truncated: bool


class XApiError(Exception):
    pass


class XApiAuthError(XApiError):
    pass


class XApiNotFoundError(XApiError):
    pass


class XApiRateLimitError(XApiError):
    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _raise_for_x_status(response: httpx.Response, *, root: bool) -> None:
    if response.status_code in {401, 403}:
        raise XApiAuthError(f"X API auth failed: {response.status_code}")
    if root and response.status_code == 404:
        raise XApiNotFoundError("X post not found")
    if response.status_code == 429:
        reset = response.headers.get("x-rate-limit-reset")
        retry_after = int(reset) if reset and reset.isdigit() else None
        raise XApiRateLimitError("X API rate limited", retry_after=retry_after)
    response.raise_for_status()


def _users_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    includes = payload.get("includes")
    if not isinstance(includes, dict):
        return {}
    users = includes.get("users")
    if not isinstance(users, list):
        return {}
    return {
        str(user["id"]): user
        for user in users
        if isinstance(user, dict) and isinstance(user.get("id"), str)
    }


def _reply_parent(tweet: dict[str, Any]) -> str | None:
    refs = tweet.get("referenced_tweets")
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if (
            isinstance(ref, dict)
            and ref.get("type") == "replied_to"
            and isinstance(ref.get("id"), str)
        ):
            return ref["id"]
    return None


def _tweet_from_payload(tweet: dict[str, Any], users: dict[str, dict[str, Any]]) -> XTweet:
    author_id = str(tweet.get("author_id") or "")
    user = users.get(author_id, {})
    username = user.get("username")
    name = user.get("name")
    return XTweet(
        id=str(tweet["id"]),
        text=str(tweet.get("text") or ""),
        author_id=author_id,
        author_handle=username if isinstance(username, str) and username else author_id,
        author_name=name if isinstance(name, str) and name else author_id,
        created_at=datetime.fromisoformat(str(tweet["created_at"]).replace("Z", "+00:00")),
        in_reply_to_status_id=_reply_parent(tweet),
    )


async def fetch_x_conversation(
    post_id: str,
    *,
    bearer: str,
    http: httpx.AsyncClient,
    max_replies: int = 200,
) -> XConversation:
    headers = {"Authorization": f"Bearer {bearer}"}
    root_response = await http.get(
        f"{_API_BASE}/2/tweets/{post_id}",
        headers=headers,
        params={
            "expansions": "author_id",
            "tweet.fields": _TWEET_FIELDS,
            "user.fields": _USER_FIELDS,
        },
    )
    _raise_for_x_status(root_response, root=True)
    root_payload = root_response.json()
    root_data = root_payload.get("data")
    if not isinstance(root_data, dict):
        raise XApiNotFoundError("X post payload missing data")
    root = _tweet_from_payload(root_data, _users_by_id(root_payload))
    conversation_id = str(root_data.get("conversation_id") or post_id)

    replies: list[XTweet] = []
    raw_count = 0
    next_token: str | None = None
    truncated = False
    while len(replies) < max_replies:
        params = {
            "query": f"conversation_id:{conversation_id}",
            "max_results": "100",
            "expansions": "author_id,referenced_tweets.id",
            "tweet.fields": _TWEET_FIELDS,
            "user.fields": _USER_FIELDS,
        }
        if next_token is not None:
            params["next_token"] = next_token
        response = await http.get(
            f"{_API_BASE}/2/tweets/search/recent",
            headers=headers,
            params=params,
        )
        _raise_for_x_status(response, root=False)
        payload = response.json()
        users = _users_by_id(payload)
        data = payload.get("data")
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if str(item.get("id")) == root.id:
                    continue
                raw_count += 1
                if len(replies) >= max_replies:
                    truncated = True
                    break
                replies.append(_tweet_from_payload(item, users))
        meta = payload.get("meta")
        token = meta.get("next_token") if isinstance(meta, dict) else None
        next_token = token if isinstance(token, str) and token else None
        if len(replies) >= max_replies and next_token is not None:
            truncated = True
        if next_token is None or truncated:
            break

    return XConversation(
        root=root,
        replies=replies,
        raw_count=raw_count,
        truncated=truncated,
    )


__all__ = [
    "XApiAuthError",
    "XApiError",
    "XApiNotFoundError",
    "XApiRateLimitError",
    "XConversation",
    "XTweet",
    "fetch_x_conversation",
]
