from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.sim_channel_message_list_response import SimChannelMessageListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    simulation_id: UUID,
    *,
    pagesize: int | Unset = 20,
    before: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["page[size]"] = pagesize

    json_before: None | str | Unset
    if isinstance(before, Unset):
        json_before = UNSET
    elif isinstance(before, UUID):
        json_before = str(before)
    else:
        json_before = before
    params["before"] = json_before

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/simulations/{simulation_id}/channel-messages".format(
            simulation_id=quote(str(simulation_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | SimChannelMessageListResponse | None:
    if response.status_code == 200:
        response_200 = SimChannelMessageListResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | SimChannelMessageListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagesize: int | Unset = 20,
    before: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | SimChannelMessageListResponse]:
    """List Channel Messages

    Args:
        simulation_id (UUID):
        pagesize (int | Unset):  Default: 20.
        before (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SimChannelMessageListResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagesize=pagesize,
        before=before,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagesize: int | Unset = 20,
    before: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | SimChannelMessageListResponse | None:
    """List Channel Messages

    Args:
        simulation_id (UUID):
        pagesize (int | Unset):  Default: 20.
        before (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SimChannelMessageListResponse
    """

    return sync_detailed(
        simulation_id=simulation_id,
        client=client,
        pagesize=pagesize,
        before=before,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagesize: int | Unset = 20,
    before: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | SimChannelMessageListResponse]:
    """List Channel Messages

    Args:
        simulation_id (UUID):
        pagesize (int | Unset):  Default: 20.
        before (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | SimChannelMessageListResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagesize=pagesize,
        before=before,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagesize: int | Unset = 20,
    before: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | SimChannelMessageListResponse | None:
    """List Channel Messages

    Args:
        simulation_id (UUID):
        pagesize (int | Unset):  Default: 20.
        before (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | SimChannelMessageListResponse
    """

    return (
        await asyncio_detailed(
            simulation_id=simulation_id,
            client=client,
            pagesize=pagesize,
            before=before,
            x_api_key=x_api_key,
        )
    ).parsed
