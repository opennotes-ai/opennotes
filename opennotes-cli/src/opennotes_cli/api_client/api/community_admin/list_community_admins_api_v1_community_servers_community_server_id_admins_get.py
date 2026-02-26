from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_admin_response import CommunityAdminResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: str,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/community-servers/{community_server_id}/admins".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | list[CommunityAdminResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = CommunityAdminResponse.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[Any | HTTPValidationError | list[CommunityAdminResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | list[CommunityAdminResponse]]:
    """List Community Admins

     List all admins for a specific community server.

    Returns admins with their sources of admin privileges:
    - Open Notes platform admin (is_opennotes_admin=True)
    - Community admin (role='admin')
    - Discord Manage Server permission (checked by Discord bot)

    Args:
        community_server_id: Discord guild ID
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        List of CommunityAdminResponse with admin information

    Raises:
        HTTPException 404: Community server not found
        HTTPException 403: Not authorized

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[CommunityAdminResponse]]
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
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | list[CommunityAdminResponse] | None:
    """List Community Admins

     List all admins for a specific community server.

    Returns admins with their sources of admin privileges:
    - Open Notes platform admin (is_opennotes_admin=True)
    - Community admin (role='admin')
    - Discord Manage Server permission (checked by Discord bot)

    Args:
        community_server_id: Discord guild ID
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        List of CommunityAdminResponse with admin information

    Raises:
        HTTPException 404: Community server not found
        HTTPException 403: Not authorized

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[CommunityAdminResponse]
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | list[CommunityAdminResponse]]:
    """List Community Admins

     List all admins for a specific community server.

    Returns admins with their sources of admin privileges:
    - Open Notes platform admin (is_opennotes_admin=True)
    - Community admin (role='admin')
    - Discord Manage Server permission (checked by Discord bot)

    Args:
        community_server_id: Discord guild ID
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        List of CommunityAdminResponse with admin information

    Raises:
        HTTPException 404: Community server not found
        HTTPException 403: Not authorized

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | list[CommunityAdminResponse]]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | list[CommunityAdminResponse] | None:
    """List Community Admins

     List all admins for a specific community server.

    Returns admins with their sources of admin privileges:
    - Open Notes platform admin (is_opennotes_admin=True)
    - Community admin (role='admin')
    - Discord Manage Server permission (checked by Discord bot)

    Args:
        community_server_id: Discord guild ID
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        List of CommunityAdminResponse with admin information

    Raises:
        HTTPException 404: Community server not found
        HTTPException 403: Not authorized

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | list[CommunityAdminResponse]
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
