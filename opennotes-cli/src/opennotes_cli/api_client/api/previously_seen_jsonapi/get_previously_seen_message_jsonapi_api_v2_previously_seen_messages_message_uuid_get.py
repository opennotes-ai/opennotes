from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.previously_seen_message_single_response import (
    PreviouslySeenMessageSingleResponse,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    message_uuid: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/previously-seen-messages/{message_uuid}".format(
            message_uuid=quote(str(message_uuid), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | PreviouslySeenMessageSingleResponse | None:
    if response.status_code == 200:
        response_200 = PreviouslySeenMessageSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | PreviouslySeenMessageSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    message_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | PreviouslySeenMessageSingleResponse]:
    """Get Previously Seen Message Jsonapi

     Get a single previously seen message by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.

    Args:
        message_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PreviouslySeenMessageSingleResponse]
    """

    kwargs = _get_kwargs(
        message_uuid=message_uuid,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    message_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | PreviouslySeenMessageSingleResponse | None:
    """Get Previously Seen Message Jsonapi

     Get a single previously seen message by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.

    Args:
        message_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PreviouslySeenMessageSingleResponse
    """

    return sync_detailed(
        message_uuid=message_uuid,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    message_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | PreviouslySeenMessageSingleResponse]:
    """Get Previously Seen Message Jsonapi

     Get a single previously seen message by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.

    Args:
        message_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PreviouslySeenMessageSingleResponse]
    """

    kwargs = _get_kwargs(
        message_uuid=message_uuid,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    message_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | PreviouslySeenMessageSingleResponse | None:
    """Get Previously Seen Message Jsonapi

     Get a single previously seen message by ID with JSON:API format.

    Returns JSON:API formatted response with data and jsonapi keys.
    Returns JSON:API error format for 404 and other errors.

    Args:
        message_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PreviouslySeenMessageSingleResponse
    """

    return (
        await asyncio_detailed(
            message_uuid=message_uuid,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
