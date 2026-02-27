from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_server_single_response import CommunityServerSingleResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    platform: str | Unset = "discord",
    platform_community_server_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["platform"] = platform

    params["platform_community_server_id"] = platform_community_server_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/community-servers/lookup",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CommunityServerSingleResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CommunityServerSingleResponse.from_dict(response.json())

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
) -> Response[Any | CommunityServerSingleResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_community_server_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityServerSingleResponse | HTTPValidationError]:
    r"""Lookup Community Server Jsonapi

     Look up a community server by platform and platform ID with JSON:API format.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        JSON:API formatted response with community server details

    Raises:
        404: If community server not found and user is not a service account

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityServerSingleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform=platform,
        platform_community_server_id=platform_community_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_community_server_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityServerSingleResponse | HTTPValidationError | None:
    r"""Lookup Community Server Jsonapi

     Look up a community server by platform and platform ID with JSON:API format.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        JSON:API formatted response with community server details

    Raises:
        404: If community server not found and user is not a service account

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityServerSingleResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        platform=platform,
        platform_community_server_id=platform_community_server_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_community_server_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityServerSingleResponse | HTTPValidationError]:
    r"""Lookup Community Server Jsonapi

     Look up a community server by platform and platform ID with JSON:API format.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        JSON:API formatted response with community server details

    Raises:
        404: If community server not found and user is not a service account

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityServerSingleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform=platform,
        platform_community_server_id=platform_community_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_community_server_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityServerSingleResponse | HTTPValidationError | None:
    r"""Lookup Community Server Jsonapi

     Look up a community server by platform and platform ID with JSON:API format.

    Returns the internal UUID for a community server based on its platform-specific identifier.
    Auto-creates the community server if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)

    Returns:
        JSON:API formatted response with community server details

    Raises:
        404: If community server not found and user is not a service account

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_community_server_id (str): Platform-specific ID (e.g., Discord guild ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityServerSingleResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            platform=platform,
            platform_community_server_id=platform_community_server_id,
            x_api_key=x_api_key,
        )
    ).parsed
