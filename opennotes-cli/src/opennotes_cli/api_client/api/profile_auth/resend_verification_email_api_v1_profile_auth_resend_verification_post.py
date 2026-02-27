from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.resend_verification_email_api_v1_profile_auth_resend_verification_post_response_resend_verification_email_api_v1_profile_auth_resend_verification_post import (
    ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost,
)
from ...types import UNSET, Response


def _get_kwargs(
    *,
    email: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["email"] = email

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/profile/auth/resend-verification",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
    | None
):
    if response.status_code == 200:
        response_200 = ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost.from_dict(
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
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
]:
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
) -> Response[
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
]:
    """Resend Verification Email

     Resend email verification to a user.

    This endpoint:
    1. Finds the identity by email
    2. Checks if email is already verified
    3. Generates new verification token
    4. Sends new verification email

    Args:
        email: The email address to resend verification to
        db: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException 400: If email not found or already verified

    Args:
        email (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost]
    """

    kwargs = _get_kwargs(
        email=email,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    email: str,
) -> (
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
    | None
):
    """Resend Verification Email

     Resend email verification to a user.

    This endpoint:
    1. Finds the identity by email
    2. Checks if email is already verified
    3. Generates new verification token
    4. Sends new verification email

    Args:
        email: The email address to resend verification to
        db: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException 400: If email not found or already verified

    Args:
        email (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
    """

    return sync_detailed(
        client=client,
        email=email,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    email: str,
) -> Response[
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
]:
    """Resend Verification Email

     Resend email verification to a user.

    This endpoint:
    1. Finds the identity by email
    2. Checks if email is already verified
    3. Generates new verification token
    4. Sends new verification email

    Args:
        email: The email address to resend verification to
        db: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException 400: If email not found or already verified

    Args:
        email (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost]
    """

    kwargs = _get_kwargs(
        email=email,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    email: str,
) -> (
    HTTPValidationError
    | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
    | None
):
    """Resend Verification Email

     Resend email verification to a user.

    This endpoint:
    1. Finds the identity by email
    2. Checks if email is already verified
    3. Generates new verification token
    4. Sends new verification email

    Args:
        email: The email address to resend verification to
        db: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException 400: If email not found or already verified

    Args:
        email (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResendVerificationEmailApiV1ProfileAuthResendVerificationPostResponseResendVerificationEmailApiV1ProfileAuthResendVerificationPost
    """

    return (
        await asyncio_detailed(
            client=client,
            email=email,
        )
    ).parsed
