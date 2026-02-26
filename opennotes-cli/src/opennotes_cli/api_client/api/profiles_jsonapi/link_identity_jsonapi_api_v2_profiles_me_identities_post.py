from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.identity_create_request import IdentityCreateRequest
from ...models.identity_single_response import IdentitySingleResponse
from ...types import Response


def _get_kwargs(
    *,
    body: IdentityCreateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/profiles/me/identities",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | IdentitySingleResponse | None:
    if response.status_code == 201:
        response_201 = IdentitySingleResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | IdentitySingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: IdentityCreateRequest,
) -> Response[HTTPValidationError | IdentitySingleResponse]:
    """Link Identity Jsonapi

     Link a new authentication identity to the current user's profile.

    JSON:API POST request should use standard JSON:API request body format
    with data object containing type and attributes.

    Security: Requires oauth_verified in credentials to prevent linking
    accounts the user doesn't own.

    Args:
        body (IdentityCreateRequest): JSON:API request for creating an identity.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | IdentitySingleResponse]
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
    body: IdentityCreateRequest,
) -> HTTPValidationError | IdentitySingleResponse | None:
    """Link Identity Jsonapi

     Link a new authentication identity to the current user's profile.

    JSON:API POST request should use standard JSON:API request body format
    with data object containing type and attributes.

    Security: Requires oauth_verified in credentials to prevent linking
    accounts the user doesn't own.

    Args:
        body (IdentityCreateRequest): JSON:API request for creating an identity.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | IdentitySingleResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: IdentityCreateRequest,
) -> Response[HTTPValidationError | IdentitySingleResponse]:
    """Link Identity Jsonapi

     Link a new authentication identity to the current user's profile.

    JSON:API POST request should use standard JSON:API request body format
    with data object containing type and attributes.

    Security: Requires oauth_verified in credentials to prevent linking
    accounts the user doesn't own.

    Args:
        body (IdentityCreateRequest): JSON:API request for creating an identity.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | IdentitySingleResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: IdentityCreateRequest,
) -> HTTPValidationError | IdentitySingleResponse | None:
    """Link Identity Jsonapi

     Link a new authentication identity to the current user's profile.

    JSON:API POST request should use standard JSON:API request body format
    with data object containing type and attributes.

    Security: Requires oauth_verified in credentials to prevent linking
    accounts the user doesn't own.

    Args:
        body (IdentityCreateRequest): JSON:API request for creating an identity.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | IdentitySingleResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
