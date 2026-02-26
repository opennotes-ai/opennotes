from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.welcome_message_update_request import WelcomeMessageUpdateRequest
from ...models.welcome_message_update_response import WelcomeMessageUpdateResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    platform_community_server_id: str,
    *,
    body: WelcomeMessageUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/community-servers/{platform_community_server_id}/welcome-message".format(
            platform_community_server_id=quote(
                str(platform_community_server_id), safe=""
            ),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | WelcomeMessageUpdateResponse | None:
    if response.status_code == 200:
        response_200 = WelcomeMessageUpdateResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | WelcomeMessageUpdateResponse]:
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
    body: WelcomeMessageUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | WelcomeMessageUpdateResponse]:
    """Update Welcome Message

     Update the welcome message ID for a community server.

    This endpoint is typically called by the Discord bot after posting and pinning
    a welcome message in the bot channel. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the welcome_message_id to set (or null to clear)

    Returns:
        Updated community server welcome message info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        x_api_key (None | str | Unset):
        body (WelcomeMessageUpdateRequest): Request model for updating welcome message ID.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | WelcomeMessageUpdateResponse]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
        body=body,
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
    body: WelcomeMessageUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | WelcomeMessageUpdateResponse | None:
    """Update Welcome Message

     Update the welcome message ID for a community server.

    This endpoint is typically called by the Discord bot after posting and pinning
    a welcome message in the bot channel. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the welcome_message_id to set (or null to clear)

    Returns:
        Updated community server welcome message info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        x_api_key (None | str | Unset):
        body (WelcomeMessageUpdateRequest): Request model for updating welcome message ID.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | WelcomeMessageUpdateResponse
    """

    return sync_detailed(
        platform_community_server_id=platform_community_server_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: WelcomeMessageUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | WelcomeMessageUpdateResponse]:
    """Update Welcome Message

     Update the welcome message ID for a community server.

    This endpoint is typically called by the Discord bot after posting and pinning
    a welcome message in the bot channel. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the welcome_message_id to set (or null to clear)

    Returns:
        Updated community server welcome message info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        x_api_key (None | str | Unset):
        body (WelcomeMessageUpdateRequest): Request model for updating welcome message ID.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | WelcomeMessageUpdateResponse]
    """

    kwargs = _get_kwargs(
        platform_community_server_id=platform_community_server_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    platform_community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: WelcomeMessageUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | WelcomeMessageUpdateResponse | None:
    """Update Welcome Message

     Update the welcome message ID for a community server.

    This endpoint is typically called by the Discord bot after posting and pinning
    a welcome message in the bot channel. Only service accounts (bots) can call this.

    Args:
        platform_community_server_id: Platform-specific ID (e.g., Discord guild ID)
        request_body: Contains the welcome_message_id to set (or null to clear)

    Returns:
        Updated community server welcome message info

    Raises:
        401: If not authenticated
        403: If not a service account
        404: If community server not found

    Args:
        platform_community_server_id (str):
        x_api_key (None | str | Unset):
        body (WelcomeMessageUpdateRequest): Request model for updating welcome message ID.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | WelcomeMessageUpdateResponse
    """

    return (
        await asyncio_detailed(
            platform_community_server_id=platform_community_server_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
