from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.bulk_scan_create_jsonapi_request import BulkScanCreateJSONAPIRequest
from ...models.bulk_scan_single_response import BulkScanSingleResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: BulkScanCreateJSONAPIRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/bulk-scans",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | BulkScanSingleResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = BulkScanSingleResponse.from_dict(response.json())

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
) -> Response[Any | BulkScanSingleResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BulkScanCreateJSONAPIRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BulkScanSingleResponse | HTTPValidationError]:
    r"""Initiate Scan

     Initiate a new bulk content scan.

    JSON:API request body must contain:
    - data.type: \"bulk-scans\"
    - data.attributes.community_server_id: UUID of community to scan
    - data.attributes.scan_window_days: Number of days to scan back (1-30)
    - data.attributes.channel_ids: Optional list of specific channel IDs

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Returns a bulk-scans resource with scan_id and initial status.

    Args:
        x_api_key (None | str | Unset):
        body (BulkScanCreateJSONAPIRequest): JSON:API request body for creating a bulk scan.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BulkScanSingleResponse | HTTPValidationError]
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
    body: BulkScanCreateJSONAPIRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BulkScanSingleResponse | HTTPValidationError | None:
    r"""Initiate Scan

     Initiate a new bulk content scan.

    JSON:API request body must contain:
    - data.type: \"bulk-scans\"
    - data.attributes.community_server_id: UUID of community to scan
    - data.attributes.scan_window_days: Number of days to scan back (1-30)
    - data.attributes.channel_ids: Optional list of specific channel IDs

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Returns a bulk-scans resource with scan_id and initial status.

    Args:
        x_api_key (None | str | Unset):
        body (BulkScanCreateJSONAPIRequest): JSON:API request body for creating a bulk scan.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BulkScanSingleResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BulkScanCreateJSONAPIRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | BulkScanSingleResponse | HTTPValidationError]:
    r"""Initiate Scan

     Initiate a new bulk content scan.

    JSON:API request body must contain:
    - data.type: \"bulk-scans\"
    - data.attributes.community_server_id: UUID of community to scan
    - data.attributes.scan_window_days: Number of days to scan back (1-30)
    - data.attributes.channel_ids: Optional list of specific channel IDs

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Returns a bulk-scans resource with scan_id and initial status.

    Args:
        x_api_key (None | str | Unset):
        body (BulkScanCreateJSONAPIRequest): JSON:API request body for creating a bulk scan.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | BulkScanSingleResponse | HTTPValidationError]
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
    body: BulkScanCreateJSONAPIRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | BulkScanSingleResponse | HTTPValidationError | None:
    r"""Initiate Scan

     Initiate a new bulk content scan.

    JSON:API request body must contain:
    - data.type: \"bulk-scans\"
    - data.attributes.community_server_id: UUID of community to scan
    - data.attributes.scan_window_days: Number of days to scan back (1-30)
    - data.attributes.channel_ids: Optional list of specific channel IDs

    Authorization: Requires admin access to the target community.
    Service accounts have unrestricted access.

    Returns a bulk-scans resource with scan_id and initial status.

    Args:
        x_api_key (None | str | Unset):
        body (BulkScanCreateJSONAPIRequest): JSON:API request body for creating a bulk scan.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | BulkScanSingleResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
