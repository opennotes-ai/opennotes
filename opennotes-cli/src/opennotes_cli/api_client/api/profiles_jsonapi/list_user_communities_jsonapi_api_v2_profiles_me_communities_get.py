from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_membership_list_response import CommunityMembershipListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/profiles/me/communities",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CommunityMembershipListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CommunityMembershipListResponse.from_dict(response.json())

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
) -> Response[Any | CommunityMembershipListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[Any | CommunityMembershipListResponse | HTTPValidationError]:
    """List User Communities Jsonapi

     List all communities the current user is a member of with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of communities to return (1-100, default 50)
        offset: Number of communities to skip (>=0, default 0)

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityMembershipListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Any | CommunityMembershipListResponse | HTTPValidationError | None:
    """List User Communities Jsonapi

     List all communities the current user is a member of with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of communities to return (1-100, default 50)
        offset: Number of communities to skip (>=0, default 0)

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityMembershipListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[Any | CommunityMembershipListResponse | HTTPValidationError]:
    """List User Communities Jsonapi

     List all communities the current user is a member of with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of communities to return (1-100, default 50)
        offset: Number of communities to skip (>=0, default 0)

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityMembershipListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Any | CommunityMembershipListResponse | HTTPValidationError | None:
    """List User Communities Jsonapi

     List all communities the current user is a member of with JSON:API format.

    Returns JSON:API formatted response with data array and jsonapi keys.

    Query Parameters:
        limit: Maximum number of communities to return (1-100, default 50)
        offset: Number of communities to skip (>=0, default 0)

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityMembershipListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            offset=offset,
        )
    ).parsed
