import datetime
from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.candidate_list_response import CandidateListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | str | Unset = UNSET,
    filterdataset_name: None | str | Unset = UNSET,
    filterdataset_tags: list[str] | None | Unset = UNSET,
    filterrating: None | str | Unset = UNSET,
    filterhas_content: bool | None | Unset = UNSET,
    filterpublished_date_from: datetime.datetime | None | Unset = UNSET,
    filterpublished_date_to: datetime.datetime | None | Unset = UNSET,
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
    else:
        json_filterstatus = filterstatus
    params["filter[status]"] = json_filterstatus

    json_filterdataset_name: None | str | Unset
    if isinstance(filterdataset_name, Unset):
        json_filterdataset_name = UNSET
    else:
        json_filterdataset_name = filterdataset_name
    params["filter[dataset_name]"] = json_filterdataset_name

    json_filterdataset_tags: list[str] | None | Unset
    if isinstance(filterdataset_tags, Unset):
        json_filterdataset_tags = UNSET
    elif isinstance(filterdataset_tags, list):
        json_filterdataset_tags = filterdataset_tags

    else:
        json_filterdataset_tags = filterdataset_tags
    params["filter[dataset_tags]"] = json_filterdataset_tags

    json_filterrating: None | str | Unset
    if isinstance(filterrating, Unset):
        json_filterrating = UNSET
    else:
        json_filterrating = filterrating
    params["filter[rating]"] = json_filterrating

    json_filterhas_content: bool | None | Unset
    if isinstance(filterhas_content, Unset):
        json_filterhas_content = UNSET
    else:
        json_filterhas_content = filterhas_content
    params["filter[has_content]"] = json_filterhas_content

    json_filterpublished_date_from: None | str | Unset
    if isinstance(filterpublished_date_from, Unset):
        json_filterpublished_date_from = UNSET
    elif isinstance(filterpublished_date_from, datetime.datetime):
        json_filterpublished_date_from = filterpublished_date_from.isoformat()
    else:
        json_filterpublished_date_from = filterpublished_date_from
    params["filter[published_date_from]"] = json_filterpublished_date_from

    json_filterpublished_date_to: None | str | Unset
    if isinstance(filterpublished_date_to, Unset):
        json_filterpublished_date_to = UNSET
    elif isinstance(filterpublished_date_to, datetime.datetime):
        json_filterpublished_date_to = filterpublished_date_to.isoformat()
    else:
        json_filterpublished_date_to = filterpublished_date_to
    params["filter[published_date_to]"] = json_filterpublished_date_to

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/fact-checking/candidates",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CandidateListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CandidateListResponse.from_dict(response.json())

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
) -> Response[Any | CandidateListResponse | HTTPValidationError]:
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
    filterstatus: None | str | Unset = UNSET,
    filterdataset_name: None | str | Unset = UNSET,
    filterdataset_tags: list[str] | None | Unset = UNSET,
    filterrating: None | str | Unset = UNSET,
    filterhas_content: bool | None | Unset = UNSET,
    filterpublished_date_from: datetime.datetime | None | Unset = UNSET,
    filterpublished_date_to: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CandidateListResponse | HTTPValidationError]:
    r"""List Candidates Jsonapi

     List fact-check candidates with filtering and pagination.

    Returns a JSON:API formatted paginated list of candidates.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by candidate status (exact match)
    - filter[dataset_name]: Filter by dataset name (exact match)
    - filter[dataset_tags]: Filter by dataset tags (array overlap)
    - filter[rating]: Filter by rating - \"null\", \"not_null\", or exact value
    - filter[has_content]: Filter by whether content exists (true/false)
    - filter[published_date_from]: Filter by published_date >= datetime
    - filter[published_date_to]: Filter by published_date <= datetime

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | str | Unset):
        filterdataset_name (None | str | Unset):
        filterdataset_tags (list[str] | None | Unset):
        filterrating (None | str | Unset): Filter by rating: 'null', 'not_null', or exact value
        filterhas_content (bool | None | Unset):
        filterpublished_date_from (datetime.datetime | None | Unset):
        filterpublished_date_to (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CandidateListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterdataset_name=filterdataset_name,
        filterdataset_tags=filterdataset_tags,
        filterrating=filterrating,
        filterhas_content=filterhas_content,
        filterpublished_date_from=filterpublished_date_from,
        filterpublished_date_to=filterpublished_date_to,
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
    filterstatus: None | str | Unset = UNSET,
    filterdataset_name: None | str | Unset = UNSET,
    filterdataset_tags: list[str] | None | Unset = UNSET,
    filterrating: None | str | Unset = UNSET,
    filterhas_content: bool | None | Unset = UNSET,
    filterpublished_date_from: datetime.datetime | None | Unset = UNSET,
    filterpublished_date_to: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CandidateListResponse | HTTPValidationError | None:
    r"""List Candidates Jsonapi

     List fact-check candidates with filtering and pagination.

    Returns a JSON:API formatted paginated list of candidates.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by candidate status (exact match)
    - filter[dataset_name]: Filter by dataset name (exact match)
    - filter[dataset_tags]: Filter by dataset tags (array overlap)
    - filter[rating]: Filter by rating - \"null\", \"not_null\", or exact value
    - filter[has_content]: Filter by whether content exists (true/false)
    - filter[published_date_from]: Filter by published_date >= datetime
    - filter[published_date_to]: Filter by published_date <= datetime

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | str | Unset):
        filterdataset_name (None | str | Unset):
        filterdataset_tags (list[str] | None | Unset):
        filterrating (None | str | Unset): Filter by rating: 'null', 'not_null', or exact value
        filterhas_content (bool | None | Unset):
        filterpublished_date_from (datetime.datetime | None | Unset):
        filterpublished_date_to (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CandidateListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterdataset_name=filterdataset_name,
        filterdataset_tags=filterdataset_tags,
        filterrating=filterrating,
        filterhas_content=filterhas_content,
        filterpublished_date_from=filterpublished_date_from,
        filterpublished_date_to=filterpublished_date_to,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | str | Unset = UNSET,
    filterdataset_name: None | str | Unset = UNSET,
    filterdataset_tags: list[str] | None | Unset = UNSET,
    filterrating: None | str | Unset = UNSET,
    filterhas_content: bool | None | Unset = UNSET,
    filterpublished_date_from: datetime.datetime | None | Unset = UNSET,
    filterpublished_date_to: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CandidateListResponse | HTTPValidationError]:
    r"""List Candidates Jsonapi

     List fact-check candidates with filtering and pagination.

    Returns a JSON:API formatted paginated list of candidates.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by candidate status (exact match)
    - filter[dataset_name]: Filter by dataset name (exact match)
    - filter[dataset_tags]: Filter by dataset tags (array overlap)
    - filter[rating]: Filter by rating - \"null\", \"not_null\", or exact value
    - filter[has_content]: Filter by whether content exists (true/false)
    - filter[published_date_from]: Filter by published_date >= datetime
    - filter[published_date_to]: Filter by published_date <= datetime

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | str | Unset):
        filterdataset_name (None | str | Unset):
        filterdataset_tags (list[str] | None | Unset):
        filterrating (None | str | Unset): Filter by rating: 'null', 'not_null', or exact value
        filterhas_content (bool | None | Unset):
        filterpublished_date_from (datetime.datetime | None | Unset):
        filterpublished_date_to (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CandidateListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        pagenumber=pagenumber,
        pagesize=pagesize,
        filterstatus=filterstatus,
        filterdataset_name=filterdataset_name,
        filterdataset_tags=filterdataset_tags,
        filterrating=filterrating,
        filterhas_content=filterhas_content,
        filterpublished_date_from=filterpublished_date_from,
        filterpublished_date_to=filterpublished_date_to,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    filterstatus: None | str | Unset = UNSET,
    filterdataset_name: None | str | Unset = UNSET,
    filterdataset_tags: list[str] | None | Unset = UNSET,
    filterrating: None | str | Unset = UNSET,
    filterhas_content: bool | None | Unset = UNSET,
    filterpublished_date_from: datetime.datetime | None | Unset = UNSET,
    filterpublished_date_to: datetime.datetime | None | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CandidateListResponse | HTTPValidationError | None:
    r"""List Candidates Jsonapi

     List fact-check candidates with filtering and pagination.

    Returns a JSON:API formatted paginated list of candidates.

    Query Parameters:
    - page[number]: Page number (default: 1)
    - page[size]: Page size (default: 20, max: 100)

    Filter Parameters:
    - filter[status]: Filter by candidate status (exact match)
    - filter[dataset_name]: Filter by dataset name (exact match)
    - filter[dataset_tags]: Filter by dataset tags (array overlap)
    - filter[rating]: Filter by rating - \"null\", \"not_null\", or exact value
    - filter[has_content]: Filter by whether content exists (true/false)
    - filter[published_date_from]: Filter by published_date >= datetime
    - filter[published_date_to]: Filter by published_date <= datetime

    Args:
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        filterstatus (None | str | Unset):
        filterdataset_name (None | str | Unset):
        filterdataset_tags (list[str] | None | Unset):
        filterrating (None | str | Unset): Filter by rating: 'null', 'not_null', or exact value
        filterhas_content (bool | None | Unset):
        filterpublished_date_from (datetime.datetime | None | Unset):
        filterpublished_date_to (datetime.datetime | None | Unset):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CandidateListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            filterstatus=filterstatus,
            filterdataset_name=filterdataset_name,
            filterdataset_tags=filterdataset_tags,
            filterrating=filterrating,
            filterhas_content=filterhas_content,
            filterpublished_date_from=filterpublished_date_from,
            filterpublished_date_to=filterpublished_date_to,
            x_api_key=x_api_key,
        )
    ).parsed
