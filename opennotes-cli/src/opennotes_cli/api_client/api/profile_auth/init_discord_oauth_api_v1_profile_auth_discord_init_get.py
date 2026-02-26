from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.discord_o_auth_init_response import DiscordOAuthInitResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/profile/auth/discord/init",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DiscordOAuthInitResponse | None:
    if response.status_code == 200:
        response_200 = DiscordOAuthInitResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DiscordOAuthInitResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[DiscordOAuthInitResponse]:
    """Init Discord Oauth

     Initialize Discord OAuth2 flow with CSRF protection.

    This endpoint:
    1. Generates a cryptographically secure state parameter
    2. Stores the state in Redis with a 10-minute TTL
    3. Returns the Discord authorization URL with the state parameter

    The client should:
    1. Store the returned state value
    2. Redirect the user to the authorization_url
    3. On callback, send both the code AND state to register/login endpoints

    Security: The state parameter prevents CSRF attacks by ensuring the OAuth
    callback was initiated by this application.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscordOAuthInitResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> DiscordOAuthInitResponse | None:
    """Init Discord Oauth

     Initialize Discord OAuth2 flow with CSRF protection.

    This endpoint:
    1. Generates a cryptographically secure state parameter
    2. Stores the state in Redis with a 10-minute TTL
    3. Returns the Discord authorization URL with the state parameter

    The client should:
    1. Store the returned state value
    2. Redirect the user to the authorization_url
    3. On callback, send both the code AND state to register/login endpoints

    Security: The state parameter prevents CSRF attacks by ensuring the OAuth
    callback was initiated by this application.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscordOAuthInitResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[DiscordOAuthInitResponse]:
    """Init Discord Oauth

     Initialize Discord OAuth2 flow with CSRF protection.

    This endpoint:
    1. Generates a cryptographically secure state parameter
    2. Stores the state in Redis with a 10-minute TTL
    3. Returns the Discord authorization URL with the state parameter

    The client should:
    1. Store the returned state value
    2. Redirect the user to the authorization_url
    3. On callback, send both the code AND state to register/login endpoints

    Security: The state parameter prevents CSRF attacks by ensuring the OAuth
    callback was initiated by this application.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DiscordOAuthInitResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> DiscordOAuthInitResponse | None:
    """Init Discord Oauth

     Initialize Discord OAuth2 flow with CSRF protection.

    This endpoint:
    1. Generates a cryptographically secure state parameter
    2. Stores the state in Redis with a 10-minute TTL
    3. Returns the Discord authorization URL with the state parameter

    The client should:
    1. Store the returned state value
    2. Redirect the user to the authorization_url
    3. On callback, send both the code AND state to register/login endpoints

    Security: The state parameter prevents CSRF attacks by ensuring the OAuth
    callback was initiated by this application.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DiscordOAuthInitResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
