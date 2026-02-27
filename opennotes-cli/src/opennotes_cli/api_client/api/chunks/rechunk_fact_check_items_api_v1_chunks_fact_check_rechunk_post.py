from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.batch_job_response import BatchJobResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    community_server_id: None | Unset | UUID = UNSET,
    batch_size: int | Unset = 100,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_community_server_id: None | str | Unset
    if isinstance(community_server_id, Unset):
        json_community_server_id = UNSET
    elif isinstance(community_server_id, UUID):
        json_community_server_id = str(community_server_id)
    else:
        json_community_server_id = community_server_id
    params["community_server_id"] = json_community_server_id

    params["batch_size"] = batch_size

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/chunks/fact-check/rechunk",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | BatchJobResponse | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = BatchJobResponse.from_dict(response.json())

        return response_201

    if response.status_code == 401:
        response_401 = cast(Any, None)
        return response_401

    if response.status_code == 403:
        response_403 = cast(Any, None)
        return response_403

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if response.status_code == 429:
        response_429 = cast(Any, None)
        return response_429

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | BatchJobResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    batch_size: int | Unset = 100,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BatchJobResponse | HTTPValidationError]:
    """Re-chunk and re-embed fact check items

     Initiates a background task to re-chunk and re-embed all fact check items. Useful for updating
    embeddings after model changes or migration to chunk-based embeddings. When community_server_id is
    provided, requires admin or moderator access. When not provided, uses global LLM credentials and
    only requires authentication. Rate limited to 1 request per minute. Returns 429 if operation already
    in progress.

    Args:
        community_server_id (None | Unset | UUID): Community server ID for LLM credentials
            (optional, uses global fallback if not provided)
        batch_size (int | Unset): Number of items to process in each batch (1-1000) Default: 100.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BatchJobResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        batch_size=batch_size,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    batch_size: int | Unset = 100,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BatchJobResponse | HTTPValidationError | None:
    """Re-chunk and re-embed fact check items

     Initiates a background task to re-chunk and re-embed all fact check items. Useful for updating
    embeddings after model changes or migration to chunk-based embeddings. When community_server_id is
    provided, requires admin or moderator access. When not provided, uses global LLM credentials and
    only requires authentication. Rate limited to 1 request per minute. Returns 429 if operation already
    in progress.

    Args:
        community_server_id (None | Unset | UUID): Community server ID for LLM credentials
            (optional, uses global fallback if not provided)
        batch_size (int | Unset): Number of items to process in each batch (1-1000) Default: 100.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BatchJobResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        community_server_id=community_server_id,
        batch_size=batch_size,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    batch_size: int | Unset = 100,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BatchJobResponse | HTTPValidationError]:
    """Re-chunk and re-embed fact check items

     Initiates a background task to re-chunk and re-embed all fact check items. Useful for updating
    embeddings after model changes or migration to chunk-based embeddings. When community_server_id is
    provided, requires admin or moderator access. When not provided, uses global LLM credentials and
    only requires authentication. Rate limited to 1 request per minute. Returns 429 if operation already
    in progress.

    Args:
        community_server_id (None | Unset | UUID): Community server ID for LLM credentials
            (optional, uses global fallback if not provided)
        batch_size (int | Unset): Number of items to process in each batch (1-1000) Default: 100.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BatchJobResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        batch_size=batch_size,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    community_server_id: None | Unset | UUID = UNSET,
    batch_size: int | Unset = 100,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BatchJobResponse | HTTPValidationError | None:
    """Re-chunk and re-embed fact check items

     Initiates a background task to re-chunk and re-embed all fact check items. Useful for updating
    embeddings after model changes or migration to chunk-based embeddings. When community_server_id is
    provided, requires admin or moderator access. When not provided, uses global LLM credentials and
    only requires authentication. Rate limited to 1 request per minute. Returns 429 if operation already
    in progress.

    Args:
        community_server_id (None | Unset | UUID): Community server ID for LLM credentials
            (optional, uses global fallback if not provided)
        batch_size (int | Unset): Number of items to process in each batch (1-1000) Default: 100.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BatchJobResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            community_server_id=community_server_id,
            batch_size=batch_size,
            x_api_key=x_api_key,
        )
    ).parsed
