from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rating_stats_single_response import RatingStatsSingleResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    note_id: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/notes/{note_id}/ratings/stats".format(
            note_id=quote(str(note_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RatingStatsSingleResponse | None:
    if response.status_code == 200:
        response_200 = RatingStatsSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RatingStatsSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    note_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RatingStatsSingleResponse]:
    """Get Rating Stats Jsonapi

     Get rating statistics for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' object containing singleton/aggregate resource
    - Resource has 'type', 'id', and 'attributes'

    Users can only view rating stats for notes in communities they are members of.
    Service accounts can view all rating stats.

    Args:
        note_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RatingStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        note_id=note_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    note_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RatingStatsSingleResponse | None:
    """Get Rating Stats Jsonapi

     Get rating statistics for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' object containing singleton/aggregate resource
    - Resource has 'type', 'id', and 'attributes'

    Users can only view rating stats for notes in communities they are members of.
    Service accounts can view all rating stats.

    Args:
        note_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RatingStatsSingleResponse
    """

    return sync_detailed(
        note_id=note_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    note_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RatingStatsSingleResponse]:
    """Get Rating Stats Jsonapi

     Get rating statistics for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' object containing singleton/aggregate resource
    - Resource has 'type', 'id', and 'attributes'

    Users can only view rating stats for notes in communities they are members of.
    Service accounts can view all rating stats.

    Args:
        note_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RatingStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        note_id=note_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    note_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RatingStatsSingleResponse | None:
    """Get Rating Stats Jsonapi

     Get rating statistics for a note with JSON:API format.

    JSON:API 1.0 requires:
    - Response with 200 OK status
    - 'data' object containing singleton/aggregate resource
    - Resource has 'type', 'id', and 'attributes'

    Users can only view rating stats for notes in communities they are members of.
    Service accounts can view all rating stats.

    Args:
        note_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RatingStatsSingleResponse
    """

    return (
        await asyncio_detailed(
            note_id=note_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
