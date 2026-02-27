from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.recent_scan_response import RecentScanResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/bulk-scans/communities/{community_server_id}/recent".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RecentScanResponse | None:
    if response.status_code == 200:
        response_200 = RecentScanResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RecentScanResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RecentScanResponse]:
    """Check Recent Scan

     Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a bulk-scan-status singleton resource with has_recent_scan boolean.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RecentScanResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RecentScanResponse | None:
    """Check Recent Scan

     Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a bulk-scan-status singleton resource with has_recent_scan boolean.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RecentScanResponse
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RecentScanResponse]:
    """Check Recent Scan

     Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a bulk-scan-status singleton resource with has_recent_scan boolean.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RecentScanResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RecentScanResponse | None:
    """Check Recent Scan

     Check if community has a recent scan within the configured window.

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a bulk-scan-status singleton resource with has_recent_scan boolean.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RecentScanResponse
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
