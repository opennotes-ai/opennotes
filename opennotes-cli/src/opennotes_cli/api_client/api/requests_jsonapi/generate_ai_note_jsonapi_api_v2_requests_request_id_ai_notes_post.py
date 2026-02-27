from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_single_response import NoteSingleResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    request_id: str,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/requests/{request_id}/ai-notes".format(
            request_id=quote(str(request_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NoteSingleResponse | None:
    if response.status_code == 201:
        response_201 = NoteSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | NoteSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    request_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteSingleResponse]:
    """Generate Ai Note Jsonapi

     Generate an AI-powered note for a specific request in JSON:API format.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns JSON:API formatted response with the generated note resource.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteSingleResponse]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    request_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteSingleResponse | None:
    """Generate Ai Note Jsonapi

     Generate an AI-powered note for a specific request in JSON:API format.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns JSON:API formatted response with the generated note resource.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteSingleResponse
    """

    return sync_detailed(
        request_id=request_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    request_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteSingleResponse]:
    """Generate Ai Note Jsonapi

     Generate an AI-powered note for a specific request in JSON:API format.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns JSON:API formatted response with the generated note resource.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteSingleResponse]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    request_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteSingleResponse | None:
    """Generate Ai Note Jsonapi

     Generate an AI-powered note for a specific request in JSON:API format.

    This endpoint triggers on-demand AI note generation for requests that have
    associated fact-check data. The AI will analyze the original message and
    the matched fact-check information to generate a helpful community note.

    Requirements:
    - Request must exist and have fact-check metadata (dataset_item_id, similarity_score, dataset_name)
    - AI note writing must be enabled for the community server
    - Rate limits: 5 per minute, 20 per hour

    Returns JSON:API formatted response with the generated note resource.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteSingleResponse
    """

    return (
        await asyncio_detailed(
            request_id=request_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
