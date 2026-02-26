from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.batch_score_request import BatchScoreRequest
from ...models.http_validation_error import HTTPValidationError
from ...models.note_score_list_response import NoteScoreListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: BatchScoreRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/scoring/notes/batch-scores",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NoteScoreListResponse | None:
    if response.status_code == 200:
        response_200 = NoteScoreListResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | NoteScoreListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BatchScoreRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteScoreListResponse]:
    r"""Get Batch Scores Jsonapi

     Get scores for multiple notes in JSON:API format.

    JSON:API request body must contain:
    - data.type: \"batch-score-requests\"
    - data.attributes.note_ids: list of note UUIDs

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as \"not found\" in the response.
    Service accounts can access all notes.

    Returns a list of note score resources with meta information about
    total requested vs found counts.

    Args:
        x_api_key (None | str | Unset):
        body (BatchScoreRequest): JSON:API request body for batch scores.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteScoreListResponse]
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
    body: BatchScoreRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteScoreListResponse | None:
    r"""Get Batch Scores Jsonapi

     Get scores for multiple notes in JSON:API format.

    JSON:API request body must contain:
    - data.type: \"batch-score-requests\"
    - data.attributes.note_ids: list of note UUIDs

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as \"not found\" in the response.
    Service accounts can access all notes.

    Returns a list of note score resources with meta information about
    total requested vs found counts.

    Args:
        x_api_key (None | str | Unset):
        body (BatchScoreRequest): JSON:API request body for batch scores.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteScoreListResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BatchScoreRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteScoreListResponse]:
    r"""Get Batch Scores Jsonapi

     Get scores for multiple notes in JSON:API format.

    JSON:API request body must contain:
    - data.type: \"batch-score-requests\"
    - data.attributes.note_ids: list of note UUIDs

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as \"not found\" in the response.
    Service accounts can access all notes.

    Returns a list of note score resources with meta information about
    total requested vs found counts.

    Args:
        x_api_key (None | str | Unset):
        body (BatchScoreRequest): JSON:API request body for batch scores.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteScoreListResponse]
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
    body: BatchScoreRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteScoreListResponse | None:
    r"""Get Batch Scores Jsonapi

     Get scores for multiple notes in JSON:API format.

    JSON:API request body must contain:
    - data.type: \"batch-score-requests\"
    - data.attributes.note_ids: list of note UUIDs

    Users can only get scores for notes in communities they are members of.
    Notes from other communities will be treated as \"not found\" in the response.
    Service accounts can access all notes.

    Returns a list of note score resources with meta information about
    total requested vs found counts.

    Args:
        x_api_key (None | str | Unset):
        body (BatchScoreRequest): JSON:API request body for batch scores.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteScoreListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
