from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_server_name_update_request import (
    CommunityServerNameUpdateRequest,
)
from ...models.community_server_name_update_response import (
    CommunityServerNameUpdateResponse,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    platform_community_server_id: str,
    *,
    body: CommunityServerNameUpdateRequest,
    platform: str | Unset = "discord",
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["platform"] = platform

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/community-servers/{platform_community_server_id}/name".format(
            platform_community_server_id=quote(
                str(platform_community_server_id), safe=""
            ),
        ),
        "params": params,
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CommunityServerNameUpdateResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CommunityServerNameUpdateResponse.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = cast(Any, None)
        return response_401

    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | CommunityServerNameUpdateResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: CommunityServerNameUpdateRequest,
    platform: str | Unset = "discord",
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityServerNameUpdateResponse | HTTPValidationError]:
    r"""Update Community Server Name

     Update the human-readable name for a community server.

    This endpoint is called by the bot to sync the server/guild name from the
    platform into the database. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the new name
        platform: Platform type (default: \"discord\")

    Returns:
        Updated community server name info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        platform (str | Unset): Platform type Default: 'discord'.
        x_api_key (None | str | Unset):
        body (CommunityServerNameUpdateRequest): Request model for updating community server name
            and stats.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityServerNameUpdateResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
        body=body,
        platform=platform,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: CommunityServerNameUpdateRequest,
    platform: str | Unset = "discord",
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityServerNameUpdateResponse | HTTPValidationError | None:
    r"""Update Community Server Name

     Update the human-readable name for a community server.

    This endpoint is called by the bot to sync the server/guild name from the
    platform into the database. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the new name
        platform: Platform type (default: \"discord\")

    Returns:
        Updated community server name info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        platform (str | Unset): Platform type Default: 'discord'.
        x_api_key (None | str | Unset):
        body (CommunityServerNameUpdateRequest): Request model for updating community server name
            and stats.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityServerNameUpdateResponse | HTTPValidationError
    """

    return sync_detailed(
        platform_community_server_id=platform_community_server_id,
        client=client,
        body=body,
        platform=platform,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: CommunityServerNameUpdateRequest,
    platform: str | Unset = "discord",
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityServerNameUpdateResponse | HTTPValidationError]:
    r"""Update Community Server Name

     Update the human-readable name for a community server.

    This endpoint is called by the bot to sync the server/guild name from the
    platform into the database. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the new name
        platform: Platform type (default: \"discord\")

    Returns:
        Updated community server name info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        platform (str | Unset): Platform type Default: 'discord'.
        x_api_key (None | str | Unset):
        body (CommunityServerNameUpdateRequest): Request model for updating community server name
            and stats.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityServerNameUpdateResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
        body=body,
        platform=platform,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: CommunityServerNameUpdateRequest,
    platform: str | Unset = "discord",
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityServerNameUpdateResponse | HTTPValidationError | None:
    r"""Update Community Server Name

     Update the human-readable name for a community server.

    This endpoint is called by the bot to sync the server/guild name from the
    platform into the database. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the new name
        platform: Platform type (default: \"discord\")

    Returns:
        Updated community server name info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        platform (str | Unset): Platform type Default: 'discord'.
        x_api_key (None | str | Unset):
        body (CommunityServerNameUpdateRequest): Request model for updating community server name
            and stats.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityServerNameUpdateResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            platform_community_server_id=platform_community_server_id,
            client=client,
            body=body,
            platform=platform,
            x_api_key=x_api_key,
        )
    ).parsed
