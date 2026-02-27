from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.discord_o_auth_register_request import DiscordOAuthRegisterRequest
from ...models.http_validation_error import HTTPValidationError
from ...models.user_profile_response import UserProfileResponse
from ...types import Response


def _get_kwargs(
    *,
    body: DiscordOAuthRegisterRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/profile/auth/register/discord",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UserProfileResponse | None:
    if response.status_code == 201:
        response_201 = UserProfileResponse.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | UserProfileResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DiscordOAuthRegisterRequest,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Register Discord

     Register a new user with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Creates a new user profile with verified Discord credentials
    5. Stores OAuth tokens securely in the credentials field

    Security: Prevents CSRF attacks via state validation and identity spoofing
    by verifying Discord ownership via OAuth2.

    Args:
        body (DiscordOAuthRegisterRequest): Request schema for Discord OAuth2 registration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: DiscordOAuthRegisterRequest,
) -> HTTPValidationError | UserProfileResponse | None:
    """Register Discord

     Register a new user with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Creates a new user profile with verified Discord credentials
    5. Stores OAuth tokens securely in the credentials field

    Security: Prevents CSRF attacks via state validation and identity spoofing
    by verifying Discord ownership via OAuth2.

    Args:
        body (DiscordOAuthRegisterRequest): Request schema for Discord OAuth2 registration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DiscordOAuthRegisterRequest,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Register Discord

     Register a new user with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Creates a new user profile with verified Discord credentials
    5. Stores OAuth tokens securely in the credentials field

    Security: Prevents CSRF attacks via state validation and identity spoofing
    by verifying Discord ownership via OAuth2.

    Args:
        body (DiscordOAuthRegisterRequest): Request schema for Discord OAuth2 registration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: DiscordOAuthRegisterRequest,
) -> HTTPValidationError | UserProfileResponse | None:
    """Register Discord

     Register a new user with Discord OAuth2.

    This endpoint:
    1. Validates the state parameter against stored state (CSRF protection)
    2. Exchanges the authorization code for an access token
    3. Fetches the user's Discord information to verify identity
    4. Creates a new user profile with verified Discord credentials
    5. Stores OAuth tokens securely in the credentials field

    Security: Prevents CSRF attacks via state validation and identity spoofing
    by verifying Discord ownership via OAuth2.

    Args:
        body (DiscordOAuthRegisterRequest): Request schema for Discord OAuth2 registration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
