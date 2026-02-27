from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.liveness_check_health_live_get_response_liveness_check_health_live_get import (
    LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health/live",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet | None:
    if response.status_code == 200:
        response_200 = (
            LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet.from_dict(
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
) -> Response[LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet]:
    """Liveness Check

     Kubernetes liveness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
) -> LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet | None:
    """Liveness Check

     Kubernetes liveness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
) -> Response[LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet]:
    """Liveness Check

     Kubernetes liveness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
) -> LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet | None:
    """Liveness Check

     Kubernetes liveness probe endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        LivenessCheckHealthLiveGetResponseLivenessCheckHealthLiveGet
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
