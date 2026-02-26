from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.clear_response import ClearResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: UUID,
    *,
    mode: str,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["mode"] = mode

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v2/community-servers/{community_server_id}/clear-notes".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ClearResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ClearResponse.from_dict(response.json())

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
) -> Response[Any | ClearResponse | HTTPValidationError]:
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
    mode: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ClearResponse | HTTPValidationError]:
    r"""Clear Notes

     Clear unpublished notes for a community server.

    Only deletes notes that are:
    - Status is \"NEEDS_MORE_RATINGS\" (unpublished)
    - NOT force-published (force_published=False)

    Published notes (CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL)
    and force-published notes are preserved.

    Deletes based on the mode:
    - \"all\": Delete all unpublished notes
    - \"<days>\": Delete unpublished notes older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either \"all\" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message

    Args:
        community_server_id (UUID):
        mode (str): 'all' or number of days (e.g., '30')
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClearResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        mode=mode,
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
    mode: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ClearResponse | HTTPValidationError | None:
    r"""Clear Notes

     Clear unpublished notes for a community server.

    Only deletes notes that are:
    - Status is \"NEEDS_MORE_RATINGS\" (unpublished)
    - NOT force-published (force_published=False)

    Published notes (CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL)
    and force-published notes are preserved.

    Deletes based on the mode:
    - \"all\": Delete all unpublished notes
    - \"<days>\": Delete unpublished notes older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either \"all\" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message

    Args:
        community_server_id (UUID):
        mode (str): 'all' or number of days (e.g., '30')
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClearResponse | HTTPValidationError
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        mode=mode,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    mode: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ClearResponse | HTTPValidationError]:
    r"""Clear Notes

     Clear unpublished notes for a community server.

    Only deletes notes that are:
    - Status is \"NEEDS_MORE_RATINGS\" (unpublished)
    - NOT force-published (force_published=False)

    Published notes (CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL)
    and force-published notes are preserved.

    Deletes based on the mode:
    - \"all\": Delete all unpublished notes
    - \"<days>\": Delete unpublished notes older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either \"all\" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message

    Args:
        community_server_id (UUID):
        mode (str): 'all' or number of days (e.g., '30')
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClearResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        mode=mode,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    mode: str,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ClearResponse | HTTPValidationError | None:
    r"""Clear Notes

     Clear unpublished notes for a community server.

    Only deletes notes that are:
    - Status is \"NEEDS_MORE_RATINGS\" (unpublished)
    - NOT force-published (force_published=False)

    Published notes (CURRENTLY_RATED_HELPFUL, CURRENTLY_RATED_NOT_HELPFUL)
    and force-published notes are preserved.

    Deletes based on the mode:
    - \"all\": Delete all unpublished notes
    - \"<days>\": Delete unpublished notes older than specified days

    Requires admin privileges for the community server.

    Args:
        community_server_id: Community server UUID
        mode: Either \"all\" or number of days
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object
        membership: Verified admin membership

    Returns:
        ClearResponse with deleted count and message

    Args:
        community_server_id (UUID):
        mode (str): 'all' or number of days (e.g., '30')
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClearResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            mode=mode,
            x_api_key=x_api_key,
        )
    ).parsed
