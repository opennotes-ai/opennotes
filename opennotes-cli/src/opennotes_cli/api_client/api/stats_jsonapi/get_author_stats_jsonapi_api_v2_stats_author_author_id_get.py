from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.participant_stats_single_response import ParticipantStatsSingleResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    author_id: UUID,
    *,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

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
        "url": "/api/v2/stats/author/{author_id}".format(
            author_id=quote(str(author_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ParticipantStatsSingleResponse | None:
    if response.status_code == 200:
        response_200 = ParticipantStatsSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | ParticipantStatsSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    author_id: UUID,
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ParticipantStatsSingleResponse]:
    """Get Author Stats Jsonapi

     Get statistics for a specific author in JSON:API format.

    Returns statistics about an author including notes created, ratings given,
    average helpfulness received, and top classification.

    Path Parameters:
    - author_id: The author's user profile UUID

    Query Parameters:
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        author_id (UUID):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ParticipantStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        author_id=author_id,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    author_id: UUID,
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ParticipantStatsSingleResponse | None:
    """Get Author Stats Jsonapi

     Get statistics for a specific author in JSON:API format.

    Returns statistics about an author including notes created, ratings given,
    average helpfulness received, and top classification.

    Path Parameters:
    - author_id: The author's user profile UUID

    Query Parameters:
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        author_id (UUID):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ParticipantStatsSingleResponse
    """

    return sync_detailed(
        author_id=author_id,
        client=client,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    author_id: UUID,
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ParticipantStatsSingleResponse]:
    """Get Author Stats Jsonapi

     Get statistics for a specific author in JSON:API format.

    Returns statistics about an author including notes created, ratings given,
    average helpfulness received, and top classification.

    Path Parameters:
    - author_id: The author's user profile UUID

    Query Parameters:
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        author_id (UUID):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ParticipantStatsSingleResponse]
    """

    kwargs = _get_kwargs(
        author_id=author_id,
        filtercommunity_server_id=filtercommunity_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    author_id: UUID,
    *,
    client: AuthenticatedClient,
    filtercommunity_server_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ParticipantStatsSingleResponse | None:
    """Get Author Stats Jsonapi

     Get statistics for a specific author in JSON:API format.

    Returns statistics about an author including notes created, ratings given,
    average helpfulness received, and top classification.

    Path Parameters:
    - author_id: The author's user profile UUID

    Query Parameters:
    - filter[community_server_id]: Filter by community server UUID

    Users can only see stats from communities they are members of.
    Service accounts can see all stats.

    Args:
        author_id (UUID):
        filtercommunity_server_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ParticipantStatsSingleResponse
    """

    return (
        await asyncio_detailed(
            author_id=author_id,
            client=client,
            filtercommunity_server_id=filtercommunity_server_id,
            x_api_key=x_api_key,
        )
    ).parsed
