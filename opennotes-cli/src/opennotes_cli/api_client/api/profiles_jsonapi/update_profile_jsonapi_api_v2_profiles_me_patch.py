from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.profile_single_response import ProfileSingleResponse
from ...models.profile_update_request import ProfileUpdateRequest
from ...types import Response


def _get_kwargs(
    *,
    body: ProfileUpdateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v2/profiles/me",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ProfileSingleResponse | None:
    if response.status_code == 200:
        response_200 = ProfileSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | ProfileSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ProfileUpdateRequest,
) -> Response[Any | HTTPValidationError | ProfileSingleResponse]:
    """Update Profile Jsonapi

     Update the authenticated user's profile with JSON:API format.

    Accepts JSON:API formatted request body with data object containing
    type, id, and attributes.

    Returns JSON:API formatted response with updated profile.

    Args:
        body (ProfileUpdateRequest): JSON:API request for updating a profile.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ProfileSingleResponse]
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
    client: AuthenticatedClient,
    body: ProfileUpdateRequest,
) -> Any | HTTPValidationError | ProfileSingleResponse | None:
    """Update Profile Jsonapi

     Update the authenticated user's profile with JSON:API format.

    Accepts JSON:API formatted request body with data object containing
    type, id, and attributes.

    Returns JSON:API formatted response with updated profile.

    Args:
        body (ProfileUpdateRequest): JSON:API request for updating a profile.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ProfileSingleResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ProfileUpdateRequest,
) -> Response[Any | HTTPValidationError | ProfileSingleResponse]:
    """Update Profile Jsonapi

     Update the authenticated user's profile with JSON:API format.

    Accepts JSON:API formatted request body with data object containing
    type, id, and attributes.

    Returns JSON:API formatted response with updated profile.

    Args:
        body (ProfileUpdateRequest): JSON:API request for updating a profile.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ProfileSingleResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ProfileUpdateRequest,
) -> Any | HTTPValidationError | ProfileSingleResponse | None:
    """Update Profile Jsonapi

     Update the authenticated user's profile with JSON:API format.

    Accepts JSON:API formatted request body with data object containing
    type, id, and attributes.

    Returns JSON:API formatted response with updated profile.

    Args:
        body (ProfileUpdateRequest): JSON:API request for updating a profile.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ProfileSingleResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
