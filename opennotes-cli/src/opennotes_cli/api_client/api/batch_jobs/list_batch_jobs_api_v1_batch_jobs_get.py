from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.batch_job_response import BatchJobResponse
from ...models.batch_job_status import BatchJobStatus
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    job_type: None | str | Unset = UNSET,
    status: BatchJobStatus | None | Unset = UNSET,
    limit: int | Unset = 50,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_job_type: None | str | Unset
    if isinstance(job_type, Unset):
        json_job_type = UNSET
    else:
        json_job_type = job_type
    params["job_type"] = json_job_type

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    elif isinstance(status, BatchJobStatus):
        json_status = status.value
    else:
        json_status = status
    params["status"] = json_status

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/batch-jobs",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | list[BatchJobResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = BatchJobResponse.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[Any | HTTPValidationError | list[BatchJobResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    job_type: None | str | Unset = UNSET,
    status: BatchJobStatus | None | Unset = UNSET,
    limit: int | Unset = 50,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | list[BatchJobResponse]]:
    """List batch jobs

     List batch jobs with optional filters for job type and status.

    Args:
        job_type (None | str | Unset): Filter by job type
        status (BatchJobStatus | None | Unset): Filter by job status
        limit (int | Unset): Maximum number of jobs to return Default: 50.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[BatchJobResponse]]
    """

    kwargs = _get_kwargs(
        job_type=job_type,
        status=status,
        limit=limit,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    job_type: None | str | Unset = UNSET,
    status: BatchJobStatus | None | Unset = UNSET,
    limit: int | Unset = 50,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | list[BatchJobResponse] | None:
    """List batch jobs

     List batch jobs with optional filters for job type and status.

    Args:
        job_type (None | str | Unset): Filter by job type
        status (BatchJobStatus | None | Unset): Filter by job status
        limit (int | Unset): Maximum number of jobs to return Default: 50.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[BatchJobResponse]
    """

    return sync_detailed(
        client=client,
        job_type=job_type,
        status=status,
        limit=limit,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    job_type: None | str | Unset = UNSET,
    status: BatchJobStatus | None | Unset = UNSET,
    limit: int | Unset = 50,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | list[BatchJobResponse]]:
    """List batch jobs

     List batch jobs with optional filters for job type and status.

    Args:
        job_type (None | str | Unset): Filter by job type
        status (BatchJobStatus | None | Unset): Filter by job status
        limit (int | Unset): Maximum number of jobs to return Default: 50.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[BatchJobResponse]]
    """

    kwargs = _get_kwargs(
        job_type=job_type,
        status=status,
        limit=limit,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    job_type: None | str | Unset = UNSET,
    status: BatchJobStatus | None | Unset = UNSET,
    limit: int | Unset = 50,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | list[BatchJobResponse] | None:
    """List batch jobs

     List batch jobs with optional filters for job type and status.

    Args:
        job_type (None | str | Unset): Filter by job type
        status (BatchJobStatus | None | Unset): Filter by job status
        limit (int | Unset): Maximum number of jobs to return Default: 50.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[BatchJobResponse]
    """

    return (
        await asyncio_detailed(
            client=client,
            job_type=job_type,
            status=status,
            limit=limit,
            x_api_key=x_api_key,
        )
    ).parsed
