from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.monitored_channel_single_response import MonitoredChannelSingleResponse
from ...models.monitored_channel_update_request import MonitoredChannelUpdateRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    channel_uuid: UUID,
    *,
    body: MonitoredChannelUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v2/monitored-channels/{channel_uuid}".format(
            channel_uuid=quote(str(channel_uuid), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | MonitoredChannelSingleResponse | None:
    if response.status_code == 200:
        response_200 = MonitoredChannelSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | MonitoredChannelSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    channel_uuid: UUID,
    *,
    client: AuthenticatedClient,
    body: MonitoredChannelUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | MonitoredChannelSingleResponse]:
    """Update Monitored Channel Jsonapi

     Update a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        channel_uuid (UUID):
        x_api_key (None | str | Unset):
        body (MonitoredChannelUpdateRequest): JSON:API request body for updating a monitored
            channel.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | MonitoredChannelSingleResponse]
    """

    kwargs = _get_kwargs(
        channel_uuid=channel_uuid,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    channel_uuid: UUID,
    *,
    client: AuthenticatedClient,
    body: MonitoredChannelUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | MonitoredChannelSingleResponse | None:
    """Update Monitored Channel Jsonapi

     Update a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        channel_uuid (UUID):
        x_api_key (None | str | Unset):
        body (MonitoredChannelUpdateRequest): JSON:API request body for updating a monitored
            channel.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | MonitoredChannelSingleResponse
    """

    return sync_detailed(
        channel_uuid=channel_uuid,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    channel_uuid: UUID,
    *,
    client: AuthenticatedClient,
    body: MonitoredChannelUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | MonitoredChannelSingleResponse]:
    """Update Monitored Channel Jsonapi

     Update a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        channel_uuid (UUID):
        x_api_key (None | str | Unset):
        body (MonitoredChannelUpdateRequest): JSON:API request body for updating a monitored
            channel.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | MonitoredChannelSingleResponse]
    """

    kwargs = _get_kwargs(
        channel_uuid=channel_uuid,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    channel_uuid: UUID,
    *,
    client: AuthenticatedClient,
    body: MonitoredChannelUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | MonitoredChannelSingleResponse | None:
    """Update Monitored Channel Jsonapi

     Update a monitored channel with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        channel_uuid (UUID):
        x_api_key (None | str | Unset):
        body (MonitoredChannelUpdateRequest): JSON:API request body for updating a monitored
            channel.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | MonitoredChannelSingleResponse
    """

    return (
        await asyncio_detailed(
            channel_uuid=channel_uuid,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
