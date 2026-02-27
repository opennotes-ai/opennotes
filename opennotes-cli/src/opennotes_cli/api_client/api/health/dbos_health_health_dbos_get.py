from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.service_status import ServiceStatus
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health/dbos",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ServiceStatus | None:
    if response.status_code == 200:
        response_200 = ServiceStatus.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ServiceStatus]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ServiceStatus]:
    """Dbos Health

     Check DBOS health and connectivity.

    Returns status information about the DBOS workflow system:
    - Whether DBOS is initialized
    - The schema name used for DBOS tables
    - Whether workflows are enabled

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ServiceStatus]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> ServiceStatus | None:
    """Dbos Health

     Check DBOS health and connectivity.

    Returns status information about the DBOS workflow system:
    - Whether DBOS is initialized
    - The schema name used for DBOS tables
    - Whether workflows are enabled

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ServiceStatus
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[ServiceStatus]:
    """Dbos Health

     Check DBOS health and connectivity.

    Returns status information about the DBOS workflow system:
    - Whether DBOS is initialized
    - The schema name used for DBOS tables
    - Whether workflows are enabled

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ServiceStatus]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> ServiceStatus | None:
    """Dbos Health

     Check DBOS health and connectivity.

    Returns status information about the DBOS workflow system:
    - Whether DBOS is initialized
    - The schema name used for DBOS tables
    - Whether workflows are enabled

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ServiceStatus
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
