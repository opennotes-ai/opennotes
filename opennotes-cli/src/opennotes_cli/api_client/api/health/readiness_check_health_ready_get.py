from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.readiness_check_health_ready_get_response_readiness_check_health_ready_get import (
    ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health/ready",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet | None:
    if response.status_code == 200:
        response_200 = (
            ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet.from_dict(
                response.json()
            )
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet]:
    """Readiness Check

     Kubernetes readiness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet | None:
    """Readiness Check

     Kubernetes readiness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet]:
    """Readiness Check

     Kubernetes readiness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet | None:
    """Readiness Check

     Kubernetes readiness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ReadinessCheckHealthReadyGetResponseReadinessCheckHealthReadyGet
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
