from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.distributed_health_check_health_distributed_get_response_distributed_health_check_health_distributed_get import (
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health/distributed",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
    | None
):
    if response.status_code == 200:
        response_200 = DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet.from_dict(
            response.json()
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
]:
    """Distributed Health Check

     Get aggregated health status across all instances.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> (
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
    | None
):
    """Distributed Health Check

     Get aggregated health status across all instances.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
]:
    """Distributed Health Check

     Get aggregated health status across all instances.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> (
    DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
    | None
):
    """Distributed Health Check

     Get aggregated health status across all instances.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DistributedHealthCheckHealthDistributedGetResponseDistributedHealthCheckHealthDistributedGet
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
