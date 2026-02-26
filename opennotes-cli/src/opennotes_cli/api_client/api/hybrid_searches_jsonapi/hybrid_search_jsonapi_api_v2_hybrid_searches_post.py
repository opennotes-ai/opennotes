from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.hybrid_search_request import HybridSearchRequest
from ...models.hybrid_search_result_response import HybridSearchResultResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: HybridSearchRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/hybrid-searches",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | HybridSearchResultResponse | None:
    if response.status_code == 200:
        response_200 = HybridSearchResultResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | HybridSearchResultResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: HybridSearchRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | HybridSearchResultResponse]:
    """Hybrid Search Jsonapi

     Perform hybrid search on fact-check items combining FTS and semantic similarity.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Executes hybrid search combining:
       - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
       - pgvector embedding similarity (cosine distance)
    5. Uses Convex Combination (CC) to fuse semantic and keyword scores
    6. Returns top matches ranked by combined CC score

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where alpha=0.7 by default (semantic-weighted).

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance

    Args:
        x_api_key (None | str | Unset):
        body (HybridSearchRequest): JSON:API request body for performing a hybrid search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HybridSearchResultResponse]
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
    body: HybridSearchRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | HybridSearchResultResponse | None:
    """Hybrid Search Jsonapi

     Perform hybrid search on fact-check items combining FTS and semantic similarity.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Executes hybrid search combining:
       - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
       - pgvector embedding similarity (cosine distance)
    5. Uses Convex Combination (CC) to fuse semantic and keyword scores
    6. Returns top matches ranked by combined CC score

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where alpha=0.7 by default (semantic-weighted).

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance

    Args:
        x_api_key (None | str | Unset):
        body (HybridSearchRequest): JSON:API request body for performing a hybrid search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HybridSearchResultResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: HybridSearchRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | HybridSearchResultResponse]:
    """Hybrid Search Jsonapi

     Perform hybrid search on fact-check items combining FTS and semantic similarity.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Executes hybrid search combining:
       - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
       - pgvector embedding similarity (cosine distance)
    5. Uses Convex Combination (CC) to fuse semantic and keyword scores
    6. Returns top matches ranked by combined CC score

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where alpha=0.7 by default (semantic-weighted).

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance

    Args:
        x_api_key (None | str | Unset):
        body (HybridSearchRequest): JSON:API request body for performing a hybrid search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | HybridSearchResultResponse]
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
    body: HybridSearchRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | HybridSearchResultResponse | None:
    """Hybrid Search Jsonapi

     Perform hybrid search on fact-check items combining FTS and semantic similarity.

    This endpoint:
    1. Verifies user is authorized member of community server
    2. Validates community server has OpenAI configuration
    3. Generates embedding using text-embedding-3-small (1536 dimensions)
    4. Executes hybrid search combining:
       - PostgreSQL full-text search (ts_rank_cd with weighted tsvector)
       - pgvector embedding similarity (cosine distance)
    5. Uses Convex Combination (CC) to fuse semantic and keyword scores
    6. Returns top matches ranked by combined CC score

    The CC formula: score = alpha * semantic_similarity + (1-alpha) * keyword_norm
    where alpha=0.7 by default (semantic-weighted).

    JSON:API 1.1 action endpoint that returns search results.

    Rate Limiting:
    - Per-user rate limit: 100 requests/hour
    - Per-community rate limits: Based on configured LLM usage limits
    - OpenAI API rate limits: Automatic detection with retry guidance

    Args:
        x_api_key (None | str | Unset):
        body (HybridSearchRequest): JSON:API request body for performing a hybrid search.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | HybridSearchResultResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
