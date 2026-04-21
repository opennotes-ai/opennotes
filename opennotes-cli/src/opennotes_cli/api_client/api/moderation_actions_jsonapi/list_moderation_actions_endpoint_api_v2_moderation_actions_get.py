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
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filteraction_state: ActionState | None | Unset = UNSET,
    filteraction_tier: ActionTier | None | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_filtercommunity_server_id: None | str | Unset
    if isinstance(filtercommunity_server_id, Unset):
        json_filtercommunity_server_id = UNSET
    elif isinstance(filtercommunity_server_id, UUID):
        json_filtercommunity_server_id = str(filtercommunity_server_id)
    else:
        json_filtercommunity_server_id = filtercommunity_server_id
    params["filter[community_server_id]"] = json_filtercommunity_server_id

    json_filteraction_state: None | str | Unset
    if isinstance(filteraction_state, Unset):
        json_filteraction_state = UNSET
    elif isinstance(filteraction_state, ActionState):
        json_filteraction_state = filteraction_state.value
    else:
        json_filteraction_state = filteraction_state
    params["filter[action_state]"] = json_filteraction_state

    json_filteraction_tier: None | str | Unset
    if isinstance(filteraction_tier, Unset):
        json_filteraction_tier = UNSET
    elif isinstance(filteraction_tier, ActionTier):
        json_filteraction_tier = filteraction_tier.value
    else:
        json_filteraction_tier = filteraction_tier
    params["filter[action_tier]"] = json_filteraction_tier

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
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filteraction_state: ActionState | None | Unset = UNSET,
    filteraction_tier: ActionTier | None | Unset = UNSET,
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
        filtercommunity_server_id (None | Unset | UUID):
        filteraction_state (ActionState | None | Unset):
        filteraction_tier (ActionTier | None | Unset):
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
        filtercommunity_server_id=filtercommunity_server_id,
        filteraction_state=filteraction_state,
        filteraction_tier=filteraction_tier,
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
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filteraction_state: ActionState | None | Unset = UNSET,
    filteraction_tier: ActionTier | None | Unset = UNSET,
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
        filtercommunity_server_id (None | Unset | UUID):
        filteraction_state (ActionState | None | Unset):
        filteraction_tier (ActionTier | None | Unset):
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
        filtercommunity_server_id=filtercommunity_server_id,
        filteraction_state=filteraction_state,
        filteraction_tier=filteraction_tier,
        limit=limit,
        offset=offset,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filteraction_state: ActionState | None | Unset = UNSET,
    filteraction_tier: ActionTier | None | Unset = UNSET,
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
        filtercommunity_server_id (None | Unset | UUID):
        filteraction_state (ActionState | None | Unset):
        filteraction_tier (ActionTier | None | Unset):
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
        filtercommunity_server_id=filtercommunity_server_id,
        filteraction_state=filteraction_state,
        filteraction_tier=filteraction_tier,
        limit=limit,
        offset=offset,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filteraction_state: ActionState | None | Unset = UNSET,
    filteraction_tier: ActionTier | None | Unset = UNSET,
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
        filtercommunity_server_id (None | Unset | UUID):
        filteraction_state (ActionState | None | Unset):
        filteraction_tier (ActionTier | None | Unset):
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
            filtercommunity_server_id=filtercommunity_server_id,
            filteraction_state=filteraction_state,
            filteraction_tier=filteraction_tier,
            limit=limit,
            offset=offset,
            x_api_key=x_api_key,
        )
    ).parsed
