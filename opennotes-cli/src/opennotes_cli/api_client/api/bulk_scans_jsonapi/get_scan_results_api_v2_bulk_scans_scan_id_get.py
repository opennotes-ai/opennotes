from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.bulk_scan_results_jsonapi_response import BulkScanResultsJSONAPIResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    scan_id: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/bulk-scans/{scan_id}".format(
            scan_id=quote(str(scan_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | BulkScanResultsJSONAPIResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BulkScanResultsJSONAPIResponse.from_dict(response.json())

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
) -> Response[Any | BulkScanResultsJSONAPIResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BulkScanResultsJSONAPIResponse | HTTPValidationError]:
    """Get Scan Results

     Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Returns the bulk scan resource with flagged messages included as related resources.
    Uses JSON:API compound documents with 'included' array.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BulkScanResultsJSONAPIResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        scan_id=scan_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BulkScanResultsJSONAPIResponse | HTTPValidationError | None:
    """Get Scan Results

     Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Returns the bulk scan resource with flagged messages included as related resources.
    Uses JSON:API compound documents with 'included' array.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BulkScanResultsJSONAPIResponse | HTTPValidationError
    """

    return sync_detailed(
        scan_id=scan_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BulkScanResultsJSONAPIResponse | HTTPValidationError]:
    """Get Scan Results

     Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Returns the bulk scan resource with flagged messages included as related resources.
    Uses JSON:API compound documents with 'included' array.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BulkScanResultsJSONAPIResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        scan_id=scan_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BulkScanResultsJSONAPIResponse | HTTPValidationError | None:
    """Get Scan Results

     Get scan status and flagged results.

    Authorization: Requires admin access to the community that was scanned.
    Service accounts have unrestricted access.

    Returns the bulk scan resource with flagged messages included as related resources.
    Uses JSON:API compound documents with 'included' array.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BulkScanResultsJSONAPIResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            scan_id=scan_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
