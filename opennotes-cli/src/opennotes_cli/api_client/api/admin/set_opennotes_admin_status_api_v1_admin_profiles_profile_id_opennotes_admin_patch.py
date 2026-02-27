from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.user_profile_response import UserProfileResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    profile_id: UUID,
    *,
    is_admin: bool,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["is_admin"] = is_admin

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v1/admin/profiles/{profile_id}/opennotes-admin".format(
            profile_id=quote(str(profile_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | UserProfileResponse | None:
    if response.status_code == 200:
        response_200 = UserProfileResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | UserProfileResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    is_admin: bool,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | UserProfileResponse]:
    """Set Opennotes Admin Status

     Grant or revoke Open Notes admin status for a user profile.

    Open Notes admins have cross-community administrative privileges. This endpoint
    is restricted to service accounts only.

    Args:
        profile_id: UUID of the profile to modify
        is_admin: True to grant admin status, False to revoke
        db: Database session
        service_account: Service account making the request

    Returns:
        UserProfileResponse: Updated profile with new admin status

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account

    Args:
        profile_id (UUID):
        is_admin (bool):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        profile_id=profile_id,
        is_admin=is_admin,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    is_admin: bool,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | UserProfileResponse | None:
    """Set Opennotes Admin Status

     Grant or revoke Open Notes admin status for a user profile.

    Open Notes admins have cross-community administrative privileges. This endpoint
    is restricted to service accounts only.

    Args:
        profile_id: UUID of the profile to modify
        is_admin: True to grant admin status, False to revoke
        db: Database session
        service_account: Service account making the request

    Returns:
        UserProfileResponse: Updated profile with new admin status

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account

    Args:
        profile_id (UUID):
        is_admin (bool):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | UserProfileResponse
    """

    return sync_detailed(
        profile_id=profile_id,
        client=client,
        is_admin=is_admin,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    is_admin: bool,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | UserProfileResponse]:
    """Set Opennotes Admin Status

     Grant or revoke Open Notes admin status for a user profile.

    Open Notes admins have cross-community administrative privileges. This endpoint
    is restricted to service accounts only.

    Args:
        profile_id: UUID of the profile to modify
        is_admin: True to grant admin status, False to revoke
        db: Database session
        service_account: Service account making the request

    Returns:
        UserProfileResponse: Updated profile with new admin status

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account

    Args:
        profile_id (UUID):
        is_admin (bool):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | UserProfileResponse]
    """

    kwargs = _get_kwargs(
        profile_id=profile_id,
        is_admin=is_admin,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    is_admin: bool,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | UserProfileResponse | None:
    """Set Opennotes Admin Status

     Grant or revoke Open Notes admin status for a user profile.

    Open Notes admins have cross-community administrative privileges. This endpoint
    is restricted to service accounts only.

    Args:
        profile_id: UUID of the profile to modify
        is_admin: True to grant admin status, False to revoke
        db: Database session
        service_account: Service account making the request

    Returns:
        UserProfileResponse: Updated profile with new admin status

    Raises:
        HTTPException 404: If profile not found
        HTTPException 403: If requester is not a service account

    Args:
        profile_id (UUID):
        is_admin (bool):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | UserProfileResponse
    """

    return (
        await asyncio_detailed(
            profile_id=profile_id,
            client=client,
            is_admin=is_admin,
            x_api_key=x_api_key,
        )
    ).parsed
