from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_publisher_post_create_request import NotePublisherPostCreateRequest
from ...models.note_publisher_post_single_response import (
    NotePublisherPostSingleResponse,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: NotePublisherPostCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/note-publisher-posts",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NotePublisherPostSingleResponse | None:
    if response.status_code == 201:
        response_201 = NotePublisherPostSingleResponse.from_dict(response.json())

        return response_201

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
) -> Response[Any | HTTPValidationError | NotePublisherPostSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: NotePublisherPostCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NotePublisherPostSingleResponse]:
    """Create Note Publisher Post Jsonapi

     Create a new note publisher post record with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        x_api_key (None | str | Unset):
        body (NotePublisherPostCreateRequest): JSON:API request body for creating a post record.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NotePublisherPostSingleResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: NotePublisherPostCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NotePublisherPostSingleResponse | None:
    """Create Note Publisher Post Jsonapi

     Create a new note publisher post record with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        x_api_key (None | str | Unset):
        body (NotePublisherPostCreateRequest): JSON:API request body for creating a post record.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NotePublisherPostSingleResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: NotePublisherPostCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NotePublisherPostSingleResponse]:
    """Create Note Publisher Post Jsonapi

     Create a new note publisher post record with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        x_api_key (None | str | Unset):
        body (NotePublisherPostCreateRequest): JSON:API request body for creating a post record.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NotePublisherPostSingleResponse]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: NotePublisherPostCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NotePublisherPostSingleResponse | None:
    """Create Note Publisher Post Jsonapi

     Create a new note publisher post record with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type' and 'attributes'
    - Response with 201 Created status
    - Response body with 'data' object containing created resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        x_api_key (None | str | Unset):
        body (NotePublisherPostCreateRequest): JSON:API request body for creating a post record.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NotePublisherPostSingleResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
