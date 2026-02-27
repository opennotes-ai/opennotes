from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_score_list_response import NoteScoreListResponse
from ...models.score_confidence import ScoreConfidence
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 10,
    min_confidence: None | ScoreConfidence | Unset = UNSET,
    tier: int | None | Unset = UNSET,
    batch_size: int | Unset = 1000,
    community_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["limit"] = limit

    json_min_confidence: None | str | Unset
    if isinstance(min_confidence, Unset):
        json_min_confidence = UNSET
    elif isinstance(min_confidence, ScoreConfidence):
        json_min_confidence = min_confidence.value
    else:
        json_min_confidence = min_confidence
    params["min_confidence"] = json_min_confidence

    json_tier: int | None | Unset
    if isinstance(tier, Unset):
        json_tier = UNSET
    else:
        json_tier = tier
    params["tier"] = json_tier

    params["batch_size"] = batch_size

    json_community_server_id: None | str | Unset
    if isinstance(community_server_id, Unset):
        json_community_server_id = UNSET
    elif isinstance(community_server_id, UUID):
        json_community_server_id = str(community_server_id)
    else:
        json_community_server_id = community_server_id
    params["community_server_id"] = json_community_server_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/scoring/notes/top",
        "params": params,
    }

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
    limit: int | Unset = 10,
    min_confidence: None | ScoreConfidence | Unset = UNSET,
    tier: int | None | Unset = UNSET,
    batch_size: int | Unset = 1000,
    community_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteScoreListResponse]:
    """Get Top Notes Jsonapi

     Get top-scored notes in JSON:API format.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - min_confidence: Filter by confidence level (no_data, provisional, standard)
    - tier: Filter by scoring tier (0-5)
    - batch_size: Processing batch size (100-5000, default 1000)
    - community_server_id: Filter by community server UUID

    Args:
        limit (int | Unset): Maximum number of notes to return Default: 10.
        min_confidence (None | ScoreConfidence | Unset): Minimum confidence level filter
        tier (int | None | Unset): Filter by scoring tier
        batch_size (int | Unset): Batch size for processing Default: 1000.
        community_server_id (None | Unset | UUID): Filter by community server
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteScoreListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        min_confidence=min_confidence,
        tier=tier,
        batch_size=batch_size,
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    min_confidence: None | ScoreConfidence | Unset = UNSET,
    tier: int | None | Unset = UNSET,
    batch_size: int | Unset = 1000,
    community_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteScoreListResponse | None:
    """Get Top Notes Jsonapi

     Get top-scored notes in JSON:API format.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - min_confidence: Filter by confidence level (no_data, provisional, standard)
    - tier: Filter by scoring tier (0-5)
    - batch_size: Processing batch size (100-5000, default 1000)
    - community_server_id: Filter by community server UUID

    Args:
        limit (int | Unset): Maximum number of notes to return Default: 10.
        min_confidence (None | ScoreConfidence | Unset): Minimum confidence level filter
        tier (int | None | Unset): Filter by scoring tier
        batch_size (int | Unset): Batch size for processing Default: 1000.
        community_server_id (None | Unset | UUID): Filter by community server
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteScoreListResponse
    """

    return sync_detailed(
        client=client,
        limit=limit,
        min_confidence=min_confidence,
        tier=tier,
        batch_size=batch_size,
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    min_confidence: None | ScoreConfidence | Unset = UNSET,
    tier: int | None | Unset = UNSET,
    batch_size: int | Unset = 1000,
    community_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteScoreListResponse]:
    """Get Top Notes Jsonapi

     Get top-scored notes in JSON:API format.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - min_confidence: Filter by confidence level (no_data, provisional, standard)
    - tier: Filter by scoring tier (0-5)
    - batch_size: Processing batch size (100-5000, default 1000)
    - community_server_id: Filter by community server UUID

    Args:
        limit (int | Unset): Maximum number of notes to return Default: 10.
        min_confidence (None | ScoreConfidence | Unset): Minimum confidence level filter
        tier (int | None | Unset): Filter by scoring tier
        batch_size (int | Unset): Batch size for processing Default: 1000.
        community_server_id (None | Unset | UUID): Filter by community server
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteScoreListResponse]
    """

    kwargs = _get_kwargs(
        limit=limit,
        min_confidence=min_confidence,
        tier=tier,
        batch_size=batch_size,
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 10,
    min_confidence: None | ScoreConfidence | Unset = UNSET,
    tier: int | None | Unset = UNSET,
    batch_size: int | Unset = 1000,
    community_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteScoreListResponse | None:
    """Get Top Notes Jsonapi

     Get top-scored notes in JSON:API format.

    Users can only see notes from communities they are members of.
    Service accounts can see all notes.

    Returns the highest-scored notes with:
    - Score and confidence metadata
    - Tier information
    - Rating counts
    - Optional filtering by confidence level and tier

    Query Parameters:
    - limit: Number of results (1-100, default 10)
    - min_confidence: Filter by confidence level (no_data, provisional, standard)
    - tier: Filter by scoring tier (0-5)
    - batch_size: Processing batch size (100-5000, default 1000)
    - community_server_id: Filter by community server UUID

    Args:
        limit (int | Unset): Maximum number of notes to return Default: 10.
        min_confidence (None | ScoreConfidence | Unset): Minimum confidence level filter
        tier (int | None | Unset): Filter by scoring tier
        batch_size (int | Unset): Batch size for processing Default: 1000.
        community_server_id (None | Unset | UUID): Filter by community server
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteScoreListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            min_confidence=min_confidence,
            tier=tier,
            batch_size=batch_size,
            community_server_id=community_server_id,
            x_api_key=x_api_key,
        )
    ).parsed
