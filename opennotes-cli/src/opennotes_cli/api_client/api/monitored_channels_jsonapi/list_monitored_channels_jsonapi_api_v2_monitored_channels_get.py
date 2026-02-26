from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.monitored_channel_list_jsonapi_response import (
    MonitoredChannelListJSONAPIResponse,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filtercommunity_server_id: None | str | Unset = UNSET,
    filterenabled: bool | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["page[number]"] = pagenumber

    params["page[size]"] = pagesize

    json_filtercommunity_server_id: None | str | Unset
    if isinstance(filtercommunity_server_id, Unset):
        json_filtercommunity_server_id = UNSET
    else:
        json_filtercommunity_server_id = filtercommunity_server_id
    params["filter[community_server_id]"] = json_filtercommunity_server_id

    json_filterenabled: bool | None | Unset
    if isinstance(filterenabled, Unset):
        json_filterenabled = UNSET
    else:
        json_filterenabled = filterenabled
    params["filter[enabled]"] = json_filterenabled

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/monitored-channels",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse | None:
    if response.status_code == 200:
        response_200 = MonitoredChannelListJSONAPIResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filtercommunity_server_id: None | str | Unset = UNSET,
    filterenabled: bool | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse]:
    """List Monitored Channels Jsonapi

     List monitored channels with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[enabled]: Filter by enabled status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filtercommunity_server_id (None | str | Unset):
        filterenabled (bool | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filtercommunity_server_id=filtercommunity_server_id,
        filterenabled=filterenabled,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filtercommunity_server_id: None | str | Unset = UNSET,
    filterenabled: bool | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse | None:
    """List Monitored Channels Jsonapi

     List monitored channels with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[enabled]: Filter by enabled status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filtercommunity_server_id (None | str | Unset):
        filterenabled (bool | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse
    """

    return sync_detailed(
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        filtercommunity_server_id=filtercommunity_server_id,
        filterenabled=filterenabled,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filtercommunity_server_id: None | str | Unset = UNSET,
    filterenabled: bool | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse]:
    """List Monitored Channels Jsonapi

     List monitored channels with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[enabled]: Filter by enabled status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filtercommunity_server_id (None | str | Unset):
        filterenabled (bool | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filtercommunity_server_id=filtercommunity_server_id,
        filterenabled=filterenabled,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filtercommunity_server_id: None | str | Unset = UNSET,
    filterenabled: bool | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse | None:
    """List Monitored Channels Jsonapi

     List monitored channels with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[community_server_id]: Filter by community server platform ID (required)
    - filter[enabled]: Filter by enabled status

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filtercommunity_server_id (None | str | Unset):
        filterenabled (bool | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | MonitoredChannelListJSONAPIResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            filtercommunity_server_id=filtercommunity_server_id,
            filterenabled=filterenabled,
            x_api_key=x_api_key,
        )
    ).parsed
