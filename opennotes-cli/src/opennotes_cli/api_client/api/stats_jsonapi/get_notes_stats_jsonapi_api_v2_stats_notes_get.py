import datetime
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_stats_single_response import NoteStatsSingleResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    filterdate_from: datetime.datetime | None | Unset = UNSET,
    filterdate_to: datetime.datetime | None | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_filterdate_from: None | str | Unset
    if isinstance(filterdate_from, Unset):
        json_filterdate_from = UNSET
    elif isinstance(filterdate_from, datetime.datetime):
        json_filterdate_from = filterdate_from.isoformat()
    else:
        json_filterdate_from = filterdate_from
    params["filter[date_from]"] = json_filterdate_from

    json_filterdate_to: None | str | Unset
    if isinstance(filterdate_to, Unset):
        json_filterdate_to = UNSET
    elif isinstance(filterdate_to, datetime.datetime):
        json_filterdate_to = filterdate_to.isoformat()
    else:
        json_filterdate_to = filterdate_to
    params["filter[date_to]"] = json_filterdate_to

    json_filtercommunity_server_id: None | str | Unset
    if isinstance(filtercommunity_server_id, Unset):
        json_filtercommunity_server_id = UNSET
    elif isinstance(filtercommunity_server_id, UUID):
        json_filtercommunity_server_id = str(filtercommunity_server_id)
    else:
        json_filtercommunity_server_id = filtercommunity_server_id
    params["filter[community_server_id]"] = json_filtercommunity_server_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/stats/notes",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NoteStatsSingleResponse | None:
    if response.status_code == 200:
        response_200 = NoteStatsSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | NoteStatsSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    filterdate_from: datetime.datetime | None | Unset = UNSET,
    filterdate_to: datetime.datetime | None | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteStatsSingleResponse]:
    """Get Notes Stats Jsonapi

     Get aggregated note statistics in JSON:API format.

    Returns statistics about notes including total count, helpful/not helpful counts,
    pending count, and average helpfulness score.

    Query Parameters:
    - filter[date_from]: Notes created on or after this datetime
    - filter[date_to]: Notes created on or before this datetime
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        filterdate_from (datetime.datetime | None | Unset):
        filterdate_to (datetime.datetime | None | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        filterdate_from=filterdate_from,
        filterdate_to=filterdate_to,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    filterdate_from: datetime.datetime | None | Unset = UNSET,
    filterdate_to: datetime.datetime | None | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteStatsSingleResponse | None:
    """Get Notes Stats Jsonapi

     Get aggregated note statistics in JSON:API format.

    Returns statistics about notes including total count, helpful/not helpful counts,
    pending count, and average helpfulness score.

    Query Parameters:
    - filter[date_from]: Notes created on or after this datetime
    - filter[date_to]: Notes created on or before this datetime
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        filterdate_from (datetime.datetime | None | Unset):
        filterdate_to (datetime.datetime | None | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteStatsSingleResponse
    """

    return sync_detailed(
        client=client,
        filterdate_from=filterdate_from,
        filterdate_to=filterdate_to,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    filterdate_from: datetime.datetime | None | Unset = UNSET,
    filterdate_to: datetime.datetime | None | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteStatsSingleResponse]:
    """Get Notes Stats Jsonapi

     Get aggregated note statistics in JSON:API format.

    Returns statistics about notes including total count, helpful/not helpful counts,
    pending count, and average helpfulness score.

    Query Parameters:
    - filter[date_from]: Notes created on or after this datetime
    - filter[date_to]: Notes created on or before this datetime
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        filterdate_from (datetime.datetime | None | Unset):
        filterdate_to (datetime.datetime | None | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        filterdate_from=filterdate_from,
        filterdate_to=filterdate_to,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    filterdate_from: datetime.datetime | None | Unset = UNSET,
    filterdate_to: datetime.datetime | None | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteStatsSingleResponse | None:
    """Get Notes Stats Jsonapi

     Get aggregated note statistics in JSON:API format.

    Returns statistics about notes including total count, helpful/not helpful counts,
    pending count, and average helpfulness score.

    Query Parameters:
    - filter[date_from]: Notes created on or after this datetime
    - filter[date_to]: Notes created on or before this datetime
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        filterdate_from (datetime.datetime | None | Unset):
        filterdate_to (datetime.datetime | None | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteStatsSingleResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            filterdate_from=filterdate_from,
            filterdate_to=filterdate_to,
            filtercommunity_server_id=filtercommunity_server_id,
            x_api_key=x_api_key,
        )
    ).parsed
