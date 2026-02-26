import datetime
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.request_list_jsonapi_response import RequestListJSONAPIResponse
from ...models.request_status import RequestStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | RequestStatus | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterrequested_by: None | str | Unset = UNSET,
    filterrequested_at_gte: datetime.datetime | None | Unset = UNSET,
    filterrequested_at_lte: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["page[number]"] = pagenumber

    params["page[size]"] = pagesize

    json_filterstatus: None | str | Unset
    if isinstance(filterstatus, Unset):
        json_filterstatus = UNSET
    elif isinstance(filterstatus, RequestStatus):
        json_filterstatus = filterstatus.value
    else:
        json_filterstatus = filterstatus
    params["filter[status]"] = json_filterstatus

    json_filtercommunity_server_id: None | str | Unset
    if isinstance(filtercommunity_server_id, Unset):
        json_filtercommunity_server_id = UNSET
    elif isinstance(filtercommunity_server_id, UUID):
        json_filtercommunity_server_id = str(filtercommunity_server_id)
    else:
        json_filtercommunity_server_id = filtercommunity_server_id
    params["filter[community_server_id]"] = json_filtercommunity_server_id

    json_filterrequested_by: None | str | Unset
    if isinstance(filterrequested_by, Unset):
        json_filterrequested_by = UNSET
    else:
        json_filterrequested_by = filterrequested_by
    params["filter[requested_by]"] = json_filterrequested_by

    json_filterrequested_at_gte: None | str | Unset
    if isinstance(filterrequested_at_gte, Unset):
        json_filterrequested_at_gte = UNSET
    elif isinstance(filterrequested_at_gte, datetime.datetime):
        json_filterrequested_at_gte = filterrequested_at_gte.isoformat()
    else:
        json_filterrequested_at_gte = filterrequested_at_gte
    params["filter[requested_at__gte]"] = json_filterrequested_at_gte

    json_filterrequested_at_lte: None | str | Unset
    if isinstance(filterrequested_at_lte, Unset):
        json_filterrequested_at_lte = UNSET
    elif isinstance(filterrequested_at_lte, datetime.datetime):
        json_filterrequested_at_lte = filterrequested_at_lte.isoformat()
    else:
        json_filterrequested_at_lte = filterrequested_at_lte
    params["filter[requested_at__lte]"] = json_filterrequested_at_lte

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/requests",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RequestListJSONAPIResponse | None:
    if response.status_code == 200:
        response_200 = RequestListJSONAPIResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RequestListJSONAPIResponse]:
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
    filterstatus: None | RequestStatus | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterrequested_by: None | str | Unset = UNSET,
    filterrequested_at_gte: datetime.datetime | None | Unset = UNSET,
    filterrequested_at_lte: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RequestListJSONAPIResponse]:
    """List Requests Jsonapi

     List requests with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by request status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
    - filter[community_server_id]: Filter by community server UUID
    - filter[requested_by]: Filter by requester participant ID
    - filter[requested_at__gte]: Requests created on or after this datetime
    - filter[requested_at__lte]: Requests created on or before this datetime

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | RequestStatus | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterrequested_by (None | str | Unset):
        filterrequested_at_gte (datetime.datetime | None | Unset):
        filterrequested_at_lte (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RequestListJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filtercommunity_server_id=filtercommunity_server_id,
        filterrequested_by=filterrequested_by,
        filterrequested_at_gte=filterrequested_at_gte,
        filterrequested_at_lte=filterrequested_at_lte,
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
    filterstatus: None | RequestStatus | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterrequested_by: None | str | Unset = UNSET,
    filterrequested_at_gte: datetime.datetime | None | Unset = UNSET,
    filterrequested_at_lte: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RequestListJSONAPIResponse | None:
    """List Requests Jsonapi

     List requests with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by request status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
    - filter[community_server_id]: Filter by community server UUID
    - filter[requested_by]: Filter by requester participant ID
    - filter[requested_at__gte]: Requests created on or after this datetime
    - filter[requested_at__lte]: Requests created on or before this datetime

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | RequestStatus | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterrequested_by (None | str | Unset):
        filterrequested_at_gte (datetime.datetime | None | Unset):
        filterrequested_at_lte (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RequestListJSONAPIResponse
    """

    return sync_detailed(
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filtercommunity_server_id=filtercommunity_server_id,
        filterrequested_by=filterrequested_by,
        filterrequested_at_gte=filterrequested_at_gte,
        filterrequested_at_lte=filterrequested_at_lte,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | RequestStatus | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterrequested_by: None | str | Unset = UNSET,
    filterrequested_at_gte: datetime.datetime | None | Unset = UNSET,
    filterrequested_at_lte: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RequestListJSONAPIResponse]:
    """List Requests Jsonapi

     List requests with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by request status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
    - filter[community_server_id]: Filter by community server UUID
    - filter[requested_by]: Filter by requester participant ID
    - filter[requested_at__gte]: Requests created on or after this datetime
    - filter[requested_at__lte]: Requests created on or before this datetime

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | RequestStatus | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterrequested_by (None | str | Unset):
        filterrequested_at_gte (datetime.datetime | None | Unset):
        filterrequested_at_lte (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RequestListJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filtercommunity_server_id=filtercommunity_server_id,
        filterrequested_by=filterrequested_by,
        filterrequested_at_gte=filterrequested_at_gte,
        filterrequested_at_lte=filterrequested_at_lte,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | RequestStatus | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterrequested_by: None | str | Unset = UNSET,
    filterrequested_at_gte: datetime.datetime | None | Unset = UNSET,
    filterrequested_at_lte: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RequestListJSONAPIResponse | None:
    """List Requests Jsonapi

     List requests with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by request status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
    - filter[community_server_id]: Filter by community server UUID
    - filter[requested_by]: Filter by requester participant ID
    - filter[requested_at__gte]: Requests created on or after this datetime
    - filter[requested_at__lte]: Requests created on or before this datetime

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | RequestStatus | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterrequested_by (None | str | Unset):
        filterrequested_at_gte (datetime.datetime | None | Unset):
        filterrequested_at_lte (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RequestListJSONAPIResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            filterstatus=filterstatus,
            filtercommunity_server_id=filtercommunity_server_id,
            filterrequested_by=filterrequested_by,
            filterrequested_at_gte=filterrequested_at_gte,
            filterrequested_at_lte=filterrequested_at_lte,
            x_api_key=x_api_key,
        )
    ).parsed
