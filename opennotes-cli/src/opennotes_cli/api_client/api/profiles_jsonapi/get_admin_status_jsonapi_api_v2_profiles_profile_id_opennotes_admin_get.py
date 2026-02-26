from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.admin_status_single_response import AdminStatusSingleResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    profile_id: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/profiles/{profile_id}/opennotes-admin".format(
            profile_id=quote(str(profile_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> AdminStatusSingleResponse | Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = AdminStatusSingleResponse.from_dict(response.json())

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
) -> Response[AdminStatusSingleResponse | Any | HTTPValidationError]:
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
    x_api_key: None | str | Unset = UNSET,
) -> Response[AdminStatusSingleResponse | Any | HTTPValidationError]:
    """Get Admin Status Jsonapi

     Get the Open Notes admin status for a user profile.

    Returns JSON:API formatted response with admin status data.

    Security: This endpoint is restricted to service accounts only.

    Args:
        profile_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AdminStatusSingleResponse | Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        profile_id=profile_id,
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
    x_api_key: None | str | Unset = UNSET,
) -> AdminStatusSingleResponse | Any | HTTPValidationError | None:
    """Get Admin Status Jsonapi

     Get the Open Notes admin status for a user profile.

    Returns JSON:API formatted response with admin status data.

    Security: This endpoint is restricted to service accounts only.

    Args:
        profile_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AdminStatusSingleResponse | Any | HTTPValidationError
    """

    return sync_detailed(
        profile_id=profile_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[AdminStatusSingleResponse | Any | HTTPValidationError]:
    """Get Admin Status Jsonapi

     Get the Open Notes admin status for a user profile.

    Returns JSON:API formatted response with admin status data.

    Security: This endpoint is restricted to service accounts only.

    Args:
        profile_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[AdminStatusSingleResponse | Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        profile_id=profile_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    profile_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> AdminStatusSingleResponse | Any | HTTPValidationError | None:
    """Get Admin Status Jsonapi

     Get the Open Notes admin status for a user profile.

    Returns JSON:API formatted response with admin status data.

    Security: This endpoint is restricted to service accounts only.

    Args:
        profile_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        AdminStatusSingleResponse | Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            profile_id=profile_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
