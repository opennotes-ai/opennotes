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
    token: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["token"] = token

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/profile/auth/verify-email",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UserProfileResponse | None:
    if response.status_code == 200:
        response_200 = UserProfileResponse.from_dict(response.json())

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
    token: str,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Verify Email

     Verify a user's email address using the verification token.

    This endpoint:
    1. Validates the verification token exists and hasn't expired
    2. Marks the email as verified
    3. Clears the verification token
    4. Returns the updated profile

    Args:
        token: The email verification token sent to the user's email
        db: Database session

    Returns:
        UserProfile: The verified user profile

    Raises:
        HTTPException 400: If token is invalid or expired

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        token=token,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    token: str,
) -> HTTPValidationError | UserProfileResponse | None:
    """Verify Email

     Verify a user's email address using the verification token.

    This endpoint:
    1. Validates the verification token exists and hasn't expired
    2. Marks the email as verified
    3. Clears the verification token
    4. Returns the updated profile

    Args:
        token: The email verification token sent to the user's email
        db: Database session

    Returns:
        UserProfile: The verified user profile

    Raises:
        HTTPException 400: If token is invalid or expired

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return sync_detailed(
        client=client,
        token=token,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    token: str,
) -> Response[HTTPValidationError | UserProfileResponse]:
    """Verify Email

     Verify a user's email address using the verification token.

    This endpoint:
    1. Validates the verification token exists and hasn't expired
    2. Marks the email as verified
    3. Clears the verification token
    4. Returns the updated profile

    Args:
        token: The email verification token sent to the user's email
        db: Database session

    Returns:
        UserProfile: The verified user profile

    Raises:
        HTTPException 400: If token is invalid or expired

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        token=token,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    token: str,
) -> HTTPValidationError | UserProfileResponse | None:
    """Verify Email

     Verify a user's email address using the verification token.

    This endpoint:
    1. Validates the verification token exists and hasn't expired
    2. Marks the email as verified
    3. Clears the verification token
    4. Returns the updated profile

    Args:
        token: The email verification token sent to the user's email
        db: Database session

    Returns:
        UserProfile: The verified user profile

    Raises:
        HTTPException 400: If token is invalid or expired

    Args:
        token (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserProfileResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            token=token,
        )
    ).parsed
