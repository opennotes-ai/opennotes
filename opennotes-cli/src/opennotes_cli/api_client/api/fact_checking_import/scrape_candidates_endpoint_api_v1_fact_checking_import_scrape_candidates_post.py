from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.batch_job_response import BatchJobResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.scrape_processing_request import ScrapeProcessingRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ScrapeProcessingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/fact-checking/import/scrape-candidates",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

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
    body: ScrapeProcessingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BatchJobResponse | HTTPValidationError]:
    """Start candidate scraping batch job

     Start an asynchronous batch job to scrape content for pending candidates. Returns immediately with a
    BatchJob that can be polled for status. Use GET /api/v1/batch-jobs/{job_id} to check progress.

    Args:
        x_api_key (None | str | Unset):
        body (ScrapeProcessingRequest): Request parameters for scraping operations with rate
            limiting support.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BatchJobResponse | HTTPValidationError]
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
    body: ScrapeProcessingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BatchJobResponse | HTTPValidationError | None:
    """Start candidate scraping batch job

     Start an asynchronous batch job to scrape content for pending candidates. Returns immediately with a
    BatchJob that can be polled for status. Use GET /api/v1/batch-jobs/{job_id} to check progress.

    Args:
        x_api_key (None | str | Unset):
        body (ScrapeProcessingRequest): Request parameters for scraping operations with rate
            limiting support.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BatchJobResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ScrapeProcessingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BatchJobResponse | HTTPValidationError]:
    """Start candidate scraping batch job

     Start an asynchronous batch job to scrape content for pending candidates. Returns immediately with a
    BatchJob that can be polled for status. Use GET /api/v1/batch-jobs/{job_id} to check progress.

    Args:
        x_api_key (None | str | Unset):
        body (ScrapeProcessingRequest): Request parameters for scraping operations with rate
            limiting support.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BatchJobResponse | HTTPValidationError]
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
    body: ScrapeProcessingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BatchJobResponse | HTTPValidationError | None:
    """Start candidate scraping batch job

     Start an asynchronous batch job to scrape content for pending candidates. Returns immediately with a
    BatchJob that can be polled for status. Use GET /api/v1/batch-jobs/{job_id} to check progress.

    Args:
        x_api_key (None | str | Unset):
        body (ScrapeProcessingRequest): Request parameters for scraping operations with rate
            limiting support.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BatchJobResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
