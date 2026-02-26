from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_community_server_stats_api_v1_webhooks_stats_platform_community_server_id_get_response_get_community_server_stats_api_v1_webhooks_stats_platform_community_server_id_get import (
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    platform_community_server_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/webhooks/stats/{platform_community_server_id}".format(
            platform_community_server_id=quote(
                str(platform_community_server_id), safe=""
            ),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet.from_dict(
            response.json()
        )

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
]:
    """Get Community Server Stats

    Args:
        platform_community_server_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
    | None
):
    """Get Community Server Stats

    Args:
        platform_community_server_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet | HTTPValidationError
    """

    return sync_detailed(
        platform_community_server_id=platform_community_server_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
]:
    """Get Community Server Stats

    Args:
        platform_community_server_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet
    | HTTPValidationError
    | None
):
    """Get Community Server Stats

    Args:
        platform_community_server_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGetResponseGetCommunityServerStatsApiV1WebhooksStatsPlatformCommunityServerIdGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            platform_community_server_id=platform_community_server_id,
            client=client,
        )
    ).parsed
