import datetime
from http import HTTPStatus
from typing import Any, cast
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_classification import NoteClassification
from ...models.note_list_response import NoteListResponse
from ...models.note_status import NoteStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | NoteStatus | Unset = UNSET,
    filterstatus_neq: None | NoteStatus | Unset = UNSET,
    filterclassification: None | NoteClassification | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterauthor_id: None | str | Unset = UNSET,
    filterrequest_id: None | str | Unset = UNSET,
    filtercreated_at_gte: datetime.datetime | None | Unset = UNSET,
    filtercreated_at_lte: datetime.datetime | None | Unset = UNSET,
    filterrater_id_not_in: None | str | Unset = UNSET,
    filterrater_id: None | Unset | UUID = UNSET,
    filterplatform_message_id: None | str | Unset = UNSET,
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
    elif isinstance(filterstatus, NoteStatus):
        json_filterstatus = filterstatus.value
    else:
        json_filterstatus = filterstatus
    params["filter[status]"] = json_filterstatus

    json_filterstatus_neq: None | str | Unset
    if isinstance(filterstatus_neq, Unset):
        json_filterstatus_neq = UNSET
    elif isinstance(filterstatus_neq, NoteStatus):
        json_filterstatus_neq = filterstatus_neq.value
    else:
        json_filterstatus_neq = filterstatus_neq
    params["filter[status__neq]"] = json_filterstatus_neq

    json_filterclassification: None | str | Unset
    if isinstance(filterclassification, Unset):
        json_filterclassification = UNSET
    elif isinstance(filterclassification, NoteClassification):
        json_filterclassification = filterclassification.value
    else:
        json_filterclassification = filterclassification
    params["filter[classification]"] = json_filterclassification

    json_filtercommunity_server_id: None | str | Unset
    if isinstance(filtercommunity_server_id, Unset):
        json_filtercommunity_server_id = UNSET
    elif isinstance(filtercommunity_server_id, UUID):
        json_filtercommunity_server_id = str(filtercommunity_server_id)
    else:
        json_filtercommunity_server_id = filtercommunity_server_id
    params["filter[community_server_id]"] = json_filtercommunity_server_id

    json_filterauthor_id: None | str | Unset
    if isinstance(filterauthor_id, Unset):
        json_filterauthor_id = UNSET
    else:
        json_filterauthor_id = filterauthor_id
    params["filter[author_id]"] = json_filterauthor_id

    json_filterrequest_id: None | str | Unset
    if isinstance(filterrequest_id, Unset):
        json_filterrequest_id = UNSET
    else:
        json_filterrequest_id = filterrequest_id
    params["filter[request_id]"] = json_filterrequest_id

    json_filtercreated_at_gte: None | str | Unset
    if isinstance(filtercreated_at_gte, Unset):
        json_filtercreated_at_gte = UNSET
    elif isinstance(filtercreated_at_gte, datetime.datetime):
        json_filtercreated_at_gte = filtercreated_at_gte.isoformat()
    else:
        json_filtercreated_at_gte = filtercreated_at_gte
    params["filter[created_at__gte]"] = json_filtercreated_at_gte

    json_filtercreated_at_lte: None | str | Unset
    if isinstance(filtercreated_at_lte, Unset):
        json_filtercreated_at_lte = UNSET
    elif isinstance(filtercreated_at_lte, datetime.datetime):
        json_filtercreated_at_lte = filtercreated_at_lte.isoformat()
    else:
        json_filtercreated_at_lte = filtercreated_at_lte
    params["filter[created_at__lte]"] = json_filtercreated_at_lte

    json_filterrater_id_not_in: None | str | Unset
    if isinstance(filterrater_id_not_in, Unset):
        json_filterrater_id_not_in = UNSET
    else:
        json_filterrater_id_not_in = filterrater_id_not_in
    params["filter[rater_id__not_in]"] = json_filterrater_id_not_in

    json_filterrater_id: None | str | Unset
    if isinstance(filterrater_id, Unset):
        json_filterrater_id = UNSET
    elif isinstance(filterrater_id, UUID):
        json_filterrater_id = str(filterrater_id)
    else:
        json_filterrater_id = filterrater_id
    params["filter[rater_id]"] = json_filterrater_id

    json_filterplatform_message_id: None | str | Unset
    if isinstance(filterplatform_message_id, Unset):
        json_filterplatform_message_id = UNSET
    else:
        json_filterplatform_message_id = filterplatform_message_id
    params["filter[platform_message_id]"] = json_filterplatform_message_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/notes",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NoteListResponse | None:
    if response.status_code == 200:
        response_200 = NoteListResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | NoteListResponse]:
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
    filterstatus: None | NoteStatus | Unset = UNSET,
    filterstatus_neq: None | NoteStatus | Unset = UNSET,
    filterclassification: None | NoteClassification | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterauthor_id: None | str | Unset = UNSET,
    filterrequest_id: None | str | Unset = UNSET,
    filtercreated_at_gte: datetime.datetime | None | Unset = UNSET,
    filtercreated_at_lte: datetime.datetime | None | Unset = UNSET,
    filterrater_id_not_in: None | str | Unset = UNSET,
    filterrater_id: None | Unset | UUID = UNSET,
    filterplatform_message_id: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteListResponse]:
    """List Notes Jsonapi

     List notes with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters (equality):
    - filter[status]: Filter by note status (exact match)
    - filter[classification]: Filter by classification
    - filter[community_server_id]: Filter by community server UUID
    - filter[author_id]: Filter by author (user profile UUID)
    - filter[request_id]: Filter by request ID
    - filter[platform_message_id]: Filter by platform message ID (Discord snowflake)

    Filter Parameters (operators):
    - filter[status__neq]: Exclude notes with this status
    - filter[created_at__gte]: Notes created on or after this datetime
    - filter[created_at__lte]: Notes created on or before this datetime
    - filter[rater_id__not_in]: Exclude notes rated by these users
      (comma-separated list of user profile UUIDs)
    - filter[rater_id]: Include only notes rated by this user (user profile UUID)

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | NoteStatus | Unset):
        filterstatus_neq (None | NoteStatus | Unset):
        filterclassification (None | NoteClassification | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterauthor_id (None | str | Unset):
        filterrequest_id (None | str | Unset):
        filtercreated_at_gte (datetime.datetime | None | Unset):
        filtercreated_at_lte (datetime.datetime | None | Unset):
        filterrater_id_not_in (None | str | Unset):
        filterrater_id (None | Unset | UUID):
        filterplatform_message_id (None | str | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteListResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterstatus_neq=filterstatus_neq,
        filterclassification=filterclassification,
        filtercommunity_server_id=filtercommunity_server_id,
        filterauthor_id=filterauthor_id,
        filterrequest_id=filterrequest_id,
        filtercreated_at_gte=filtercreated_at_gte,
        filtercreated_at_lte=filtercreated_at_lte,
        filterrater_id_not_in=filterrater_id_not_in,
        filterrater_id=filterrater_id,
        filterplatform_message_id=filterplatform_message_id,
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
    filterstatus: None | NoteStatus | Unset = UNSET,
    filterstatus_neq: None | NoteStatus | Unset = UNSET,
    filterclassification: None | NoteClassification | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterauthor_id: None | str | Unset = UNSET,
    filterrequest_id: None | str | Unset = UNSET,
    filtercreated_at_gte: datetime.datetime | None | Unset = UNSET,
    filtercreated_at_lte: datetime.datetime | None | Unset = UNSET,
    filterrater_id_not_in: None | str | Unset = UNSET,
    filterrater_id: None | Unset | UUID = UNSET,
    filterplatform_message_id: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteListResponse | None:
    """List Notes Jsonapi

     List notes with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters (equality):
    - filter[status]: Filter by note status (exact match)
    - filter[classification]: Filter by classification
    - filter[community_server_id]: Filter by community server UUID
    - filter[author_id]: Filter by author (user profile UUID)
    - filter[request_id]: Filter by request ID
    - filter[platform_message_id]: Filter by platform message ID (Discord snowflake)

    Filter Parameters (operators):
    - filter[status__neq]: Exclude notes with this status
    - filter[created_at__gte]: Notes created on or after this datetime
    - filter[created_at__lte]: Notes created on or before this datetime
    - filter[rater_id__not_in]: Exclude notes rated by these users
      (comma-separated list of user profile UUIDs)
    - filter[rater_id]: Include only notes rated by this user (user profile UUID)

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | NoteStatus | Unset):
        filterstatus_neq (None | NoteStatus | Unset):
        filterclassification (None | NoteClassification | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterauthor_id (None | str | Unset):
        filterrequest_id (None | str | Unset):
        filtercreated_at_gte (datetime.datetime | None | Unset):
        filtercreated_at_lte (datetime.datetime | None | Unset):
        filterrater_id_not_in (None | str | Unset):
        filterrater_id (None | Unset | UUID):
        filterplatform_message_id (None | str | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteListResponse
    """

    return sync_detailed(
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterstatus_neq=filterstatus_neq,
        filterclassification=filterclassification,
        filtercommunity_server_id=filtercommunity_server_id,
        filterauthor_id=filterauthor_id,
        filterrequest_id=filterrequest_id,
        filtercreated_at_gte=filtercreated_at_gte,
        filtercreated_at_lte=filtercreated_at_lte,
        filterrater_id_not_in=filterrater_id_not_in,
        filterrater_id=filterrater_id,
        filterplatform_message_id=filterplatform_message_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | NoteStatus | Unset = UNSET,
    filterstatus_neq: None | NoteStatus | Unset = UNSET,
    filterclassification: None | NoteClassification | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterauthor_id: None | str | Unset = UNSET,
    filterrequest_id: None | str | Unset = UNSET,
    filtercreated_at_gte: datetime.datetime | None | Unset = UNSET,
    filtercreated_at_lte: datetime.datetime | None | Unset = UNSET,
    filterrater_id_not_in: None | str | Unset = UNSET,
    filterrater_id: None | Unset | UUID = UNSET,
    filterplatform_message_id: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteListResponse]:
    """List Notes Jsonapi

     List notes with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters (equality):
    - filter[status]: Filter by note status (exact match)
    - filter[classification]: Filter by classification
    - filter[community_server_id]: Filter by community server UUID
    - filter[author_id]: Filter by author (user profile UUID)
    - filter[request_id]: Filter by request ID
    - filter[platform_message_id]: Filter by platform message ID (Discord snowflake)

    Filter Parameters (operators):
    - filter[status__neq]: Exclude notes with this status
    - filter[created_at__gte]: Notes created on or after this datetime
    - filter[created_at__lte]: Notes created on or before this datetime
    - filter[rater_id__not_in]: Exclude notes rated by these users
      (comma-separated list of user profile UUIDs)
    - filter[rater_id]: Include only notes rated by this user (user profile UUID)

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | NoteStatus | Unset):
        filterstatus_neq (None | NoteStatus | Unset):
        filterclassification (None | NoteClassification | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterauthor_id (None | str | Unset):
        filterrequest_id (None | str | Unset):
        filtercreated_at_gte (datetime.datetime | None | Unset):
        filtercreated_at_lte (datetime.datetime | None | Unset):
        filterrater_id_not_in (None | str | Unset):
        filterrater_id (None | Unset | UUID):
        filterplatform_message_id (None | str | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteListResponse]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterstatus_neq=filterstatus_neq,
        filterclassification=filterclassification,
        filtercommunity_server_id=filtercommunity_server_id,
        filterauthor_id=filterauthor_id,
        filterrequest_id=filterrequest_id,
        filtercreated_at_gte=filtercreated_at_gte,
        filtercreated_at_lte=filtercreated_at_lte,
        filterrater_id_not_in=filterrater_id_not_in,
        filterrater_id=filterrater_id,
        filterplatform_message_id=filterplatform_message_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | NoteStatus | Unset = UNSET,
    filterstatus_neq: None | NoteStatus | Unset = UNSET,
    filterclassification: None | NoteClassification | Unset = UNSET,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    filterauthor_id: None | str | Unset = UNSET,
    filterrequest_id: None | str | Unset = UNSET,
    filtercreated_at_gte: datetime.datetime | None | Unset = UNSET,
    filtercreated_at_lte: datetime.datetime | None | Unset = UNSET,
    filterrater_id_not_in: None | str | Unset = UNSET,
    filterrater_id: None | Unset | UUID = UNSET,
    filterplatform_message_id: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteListResponse | None:
    """List Notes Jsonapi

     List notes with JSON:API format.

    Supports filtering and pagination per JSON:API specification.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters (equality):
    - filter[status]: Filter by note status (exact match)
    - filter[classification]: Filter by classification
    - filter[community_server_id]: Filter by community server UUID
    - filter[author_id]: Filter by author (user profile UUID)
    - filter[request_id]: Filter by request ID
    - filter[platform_message_id]: Filter by platform message ID (Discord snowflake)

    Filter Parameters (operators):
    - filter[status__neq]: Exclude notes with this status
    - filter[created_at__gte]: Notes created on or after this datetime
    - filter[created_at__lte]: Notes created on or before this datetime
    - filter[rater_id__not_in]: Exclude notes rated by these users
      (comma-separated list of user profile UUIDs)
    - filter[rater_id]: Include only notes rated by this user (user profile UUID)

    Returns JSON:API formatted response with data, jsonapi, links, and meta.

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | NoteStatus | Unset):
        filterstatus_neq (None | NoteStatus | Unset):
        filterclassification (None | NoteClassification | Unset):
        filtercommunity_server_id (None | Unset | UUID):
        filterauthor_id (None | str | Unset):
        filterrequest_id (None | str | Unset):
        filtercreated_at_gte (datetime.datetime | None | Unset):
        filtercreated_at_lte (datetime.datetime | None | Unset):
        filterrater_id_not_in (None | str | Unset):
        filterrater_id (None | Unset | UUID):
        filterplatform_message_id (None | str | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            filterstatus=filterstatus,
            filterstatus_neq=filterstatus_neq,
            filterclassification=filterclassification,
            filtercommunity_server_id=filtercommunity_server_id,
            filterauthor_id=filterauthor_id,
            filterrequest_id=filterrequest_id,
            filtercreated_at_gte=filtercreated_at_gte,
            filtercreated_at_lte=filtercreated_at_lte,
            filterrater_id_not_in=filterrater_id_not_in,
            filterrater_id=filterrater_id,
            filterplatform_message_id=filterplatform_message_id,
            x_api_key=x_api_key,
        )
    ).parsed
