from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.retry_response import RetryResponse
from ...models.section_slug import SectionSlug
from ...types import UNSET, Response, Unset


def _get_kwargs(
    job_id: UUID,
    slug: SectionSlug,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/url_scan/jobs/{job_id}/retry/{slug}".format(
            job_id=quote(str(job_id), safe=""),
            slug=quote(str(slug), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | RetryResponse | None:
    if response.status_code == 202:
        response_202 = RetryResponse.from_dict(response.json())

        return response_202

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | RetryResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    job_id: UUID,
    slug: SectionSlug,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RetryResponse]:
    """Retry Section

    Args:
        job_id (UUID):
        slug (SectionSlug):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RetryResponse]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        slug=slug,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    job_id: UUID,
    slug: SectionSlug,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | RetryResponse | None:
    """Retry Section

    Args:
        job_id (UUID):
        slug (SectionSlug):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RetryResponse
    """

    return sync_detailed(
        job_id=job_id,
        slug=slug,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    job_id: UUID,
    slug: SectionSlug,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | RetryResponse]:
    """Retry Section

    Args:
        job_id (UUID):
        slug (SectionSlug):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RetryResponse]
    """

    kwargs = _get_kwargs(
        job_id=job_id,
        slug=slug,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    job_id: UUID,
    slug: SectionSlug,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | RetryResponse | None:
    """Retry Section

    Args:
        job_id (UUID):
        slug (SectionSlug):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RetryResponse
    """

    return (
        await asyncio_detailed(
            job_id=job_id,
            slug=slug,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
