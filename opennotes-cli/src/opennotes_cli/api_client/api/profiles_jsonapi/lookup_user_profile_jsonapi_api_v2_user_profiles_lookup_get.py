from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.user_profile_lookup_response import UserProfileLookupResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    platform: str | Unset = "discord",
    platform_user_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["platform"] = platform

    params["platform_user_id"] = platform_user_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/user-profiles/lookup",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | UserProfileLookupResponse | None:
    if response.status_code == 200:
        response_200 = UserProfileLookupResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | UserProfileLookupResponse]:
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
    platform_user_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | UserProfileLookupResponse]:
    r"""Lookup User Profile Jsonapi

     Look up a user profile by platform and platform user ID with JSON:API format.

    Returns the internal UUID for a user profile based on its platform-specific identifier.
    Auto-creates the profile if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_user_id: Platform-specific user ID (e.g., Discord user ID)

    Returns:
        JSON:API formatted response with user profile details

    Raises:
        404: If user profile not found and user is not a service account
        400: If platform is not supported (currently only 'discord')

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_user_id (str): Platform-specific user ID (e.g., Discord user ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | UserProfileLookupResponse]
    """

    kwargs = _get_kwargs(
        platform=platform,
        platform_user_id=platform_user_id,
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
    platform_user_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | UserProfileLookupResponse | None:
    r"""Lookup User Profile Jsonapi

     Look up a user profile by platform and platform user ID with JSON:API format.

    Returns the internal UUID for a user profile based on its platform-specific identifier.
    Auto-creates the profile if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_user_id: Platform-specific user ID (e.g., Discord user ID)

    Returns:
        JSON:API formatted response with user profile details

    Raises:
        404: If user profile not found and user is not a service account
        400: If platform is not supported (currently only 'discord')

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_user_id (str): Platform-specific user ID (e.g., Discord user ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | UserProfileLookupResponse
    """

    return sync_detailed(
        client=client,
        platform=platform,
        platform_user_id=platform_user_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_user_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | UserProfileLookupResponse]:
    r"""Lookup User Profile Jsonapi

     Look up a user profile by platform and platform user ID with JSON:API format.

    Returns the internal UUID for a user profile based on its platform-specific identifier.
    Auto-creates the profile if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_user_id: Platform-specific user ID (e.g., Discord user ID)

    Returns:
        JSON:API formatted response with user profile details

    Raises:
        404: If user profile not found and user is not a service account
        400: If platform is not supported (currently only 'discord')

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_user_id (str): Platform-specific user ID (e.g., Discord user ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | UserProfileLookupResponse]
    """

    kwargs = _get_kwargs(
        platform=platform,
        platform_user_id=platform_user_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    platform: str | Unset = "discord",
    platform_user_id: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | UserProfileLookupResponse | None:
    r"""Lookup User Profile Jsonapi

     Look up a user profile by platform and platform user ID with JSON:API format.

    Returns the internal UUID for a user profile based on its platform-specific identifier.
    Auto-creates the profile if it doesn't exist (for service accounts/bots).

    Args:
        platform: Platform type (default: \"discord\")
        platform_user_id: Platform-specific user ID (e.g., Discord user ID)

    Returns:
        JSON:API formatted response with user profile details

    Raises:
        404: If user profile not found and user is not a service account
        400: If platform is not supported (currently only 'discord')

    Args:
        platform (str | Unset): Platform type Default: 'discord'.
        platform_user_id (str): Platform-specific user ID (e.g., Discord user ID)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | UserProfileLookupResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            platform=platform,
            platform_user_id=platform_user_id,
            x_api_key=x_api_key,
        )
    ).parsed
