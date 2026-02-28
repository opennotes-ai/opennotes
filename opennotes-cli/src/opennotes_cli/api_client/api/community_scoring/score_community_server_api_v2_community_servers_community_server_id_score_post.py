from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.score_community_response import ScoreCommunityResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/community-servers/{community_server_id}/score".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ScoreCommunityResponse | None:
    if response.status_code == 202:
        response_202 = ScoreCommunityResponse.from_dict(response.json())

        return response_202

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
) -> Response[Any | HTTPValidationError | ScoreCommunityResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoreCommunityResponse]:
    """Score Community Server

     Trigger manual scoring for all eligible notes in a community server.

    Admin-only. Dispatches a DBOS workflow and returns the workflow ID.
    Returns 409 if scoring is already in progress.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoreCommunityResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoreCommunityResponse | None:
    """Score Community Server

     Trigger manual scoring for all eligible notes in a community server.

    Admin-only. Dispatches a DBOS workflow and returns the workflow ID.
    Returns 409 if scoring is already in progress.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoreCommunityResponse
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoreCommunityResponse]:
    """Score Community Server

     Trigger manual scoring for all eligible notes in a community server.

    Admin-only. Dispatches a DBOS workflow and returns the workflow ID.
    Returns 409 if scoring is already in progress.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoreCommunityResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoreCommunityResponse | None:
    """Score Community Server

     Trigger manual scoring for all eligible notes in a community server.

    Admin-only. Dispatches a DBOS workflow and returns the workflow ID.
    Returns 409 if scoring is already in progress.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoreCommunityResponse
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
