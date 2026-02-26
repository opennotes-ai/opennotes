from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.user_profile_response import UserProfileResponse
from ...types import UNSET, Response


def _get_kwargs(
    *,
    email: str,
    password: str,
    display_name: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["email"] = email

    params["password"] = password

    params["display_name"] = display_name

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/profile/auth/register/email",
        "params": params,
    }

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
    email: str,
    password: str,
    display_name: str,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Register Email

    Args:
        email (str):
        password (str):
        display_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        email=email,
        password=password,
        display_name=display_name,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    email: str,
    password: str,
    display_name: str,
) -> HTTPValidationError | UserProfileResponse | None:
    """Register Email

    Args:
        email (str):
        password (str):
        display_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return sync_detailed(
        client=client,
        email=email,
        password=password,
        display_name=display_name,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    email: str,
    password: str,
    display_name: str,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Register Email

    Args:
        email (str):
        password (str):
        display_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        email=email,
        password=password,
        display_name=display_name,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    email: str,
    password: str,
    display_name: str,
) -> HTTPValidationError | UserProfileResponse | None:
    """Register Email

    Args:
        email (str):
        password (str):
        display_name (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            email=email,
            password=password,
            display_name=display_name,
        )
    ).parsed
