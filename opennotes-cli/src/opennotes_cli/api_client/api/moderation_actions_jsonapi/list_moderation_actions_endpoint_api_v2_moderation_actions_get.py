from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.action_state import ActionState
from ...models.action_tier import ActionTier
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    community_server_id: None | Unset | UUID = UNSET,
    action_state: ActionState | None | Unset = UNSET,
    action_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_community_server_id: None | str | Unset
    if isinstance(community_server_id, Unset):
        json_community_server_id = UNSET
    elif isinstance(community_server_id, UUID):
        json_community_server_id = str(community_server_id)
    else:
        json_community_server_id = community_server_id
    params["community_server_id"] = json_community_server_id

    json_action_state: None | str | Unset
    if isinstance(action_state, Unset):
        json_action_state = UNSET
    elif isinstance(action_state, ActionState):
        json_action_state = action_state.value
    else:
        json_action_state = action_state
    params["action_state"] = json_action_state

    json_action_tier: None | str | Unset
    if isinstance(action_tier, Unset):
        json_action_tier = UNSET
    elif isinstance(action_tier, ActionTier):
        json_action_tier = action_tier.value
    else:
        json_action_tier = action_tier
    params["action_tier"] = json_action_tier

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/moderation-actions",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 401:
        response_401 = cast(Any, None)
        return response_401

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    action_state: ActionState | None | Unset = UNSET,
    action_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Moderation Actions Endpoint

     List moderation actions with optional filters.

    Query params:
    - community_server_id: filter by community
    - action_state: filter by state (e.g. proposed, applied)
    - action_tier: filter by tier
    - limit: max results (default 50)
    - offset: pagination offset (default 0)

    Args:
        community_server_id (None | Unset | UUID):
        action_state (ActionState | None | Unset):
        action_tier (ActionTier | None | Unset):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        action_state=action_state,
        action_tier=action_tier,
        limit=limit,
        offset=offset,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    action_state: ActionState | None | Unset = UNSET,
    action_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Moderation Actions Endpoint

     List moderation actions with optional filters.

    Query params:
    - community_server_id: filter by community
    - action_state: filter by state (e.g. proposed, applied)
    - action_tier: filter by tier
    - limit: max results (default 50)
    - offset: pagination offset (default 0)

    Args:
        community_server_id (None | Unset | UUID):
        action_state (ActionState | None | Unset):
        action_tier (ActionTier | None | Unset):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        community_server_id=community_server_id,
        action_state=action_state,
        action_tier=action_tier,
        limit=limit,
        offset=offset,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    action_state: ActionState | None | Unset = UNSET,
    action_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Moderation Actions Endpoint

     List moderation actions with optional filters.

    Query params:
    - community_server_id: filter by community
    - action_state: filter by state (e.g. proposed, applied)
    - action_tier: filter by tier
    - limit: max results (default 50)
    - offset: pagination offset (default 0)

    Args:
        community_server_id (None | Unset | UUID):
        action_state (ActionState | None | Unset):
        action_tier (ActionTier | None | Unset):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        action_state=action_state,
        action_tier=action_tier,
        limit=limit,
        offset=offset,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    action_state: ActionState | None | Unset = UNSET,
    action_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Moderation Actions Endpoint

     List moderation actions with optional filters.

    Query params:
    - community_server_id: filter by community
    - action_state: filter by state (e.g. proposed, applied)
    - action_tier: filter by tier
    - limit: max results (default 50)
    - offset: pagination offset (default 0)

    Args:
        community_server_id (None | Unset | UUID):
        action_state (ActionState | None | Unset):
        action_tier (ActionTier | None | Unset):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            community_server_id=community_server_id,
            action_state=action_state,
            action_tier=action_tier,
            limit=limit,
            offset=offset,
            x_api_key=x_api_key,
        )
    ).parsed
