from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.remove_community_admin_response import RemoveCommunityAdminResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: str,
    user_discord_id: str,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/community-servers/{community_server_id}/admins/{user_discord_id}".format(
            community_server_id=quote(str(community_server_id), safe=""),
            user_discord_id=quote(str(user_discord_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RemoveCommunityAdminResponse | None:
    if response.status_code == 200:
        response_200 = RemoveCommunityAdminResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RemoveCommunityAdminResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    community_server_id: str,
    user_discord_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RemoveCommunityAdminResponse]:
    """Remove Community Admin

     Remove admin status from a user in a specific community server.

    Sets CommunityMember.role = 'member'. Prevents removing the last admin to ensure
    the community always has at least one admin.

    Args:
        community_server_id: Discord guild ID
        user_discord_id: Discord ID of user to demote
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        RemoveCommunityAdminResponse: Operation result

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 409: Cannot remove last admin

    Args:
        community_server_id (str):
        user_discord_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RemoveCommunityAdminResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        user_discord_id=user_discord_id,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    community_server_id: str,
    user_discord_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RemoveCommunityAdminResponse | None:
    """Remove Community Admin

     Remove admin status from a user in a specific community server.

    Sets CommunityMember.role = 'member'. Prevents removing the last admin to ensure
    the community always has at least one admin.

    Args:
        community_server_id: Discord guild ID
        user_discord_id: Discord ID of user to demote
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        RemoveCommunityAdminResponse: Operation result

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 409: Cannot remove last admin

    Args:
        community_server_id (str):
        user_discord_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RemoveCommunityAdminResponse
    """

    return sync_detailed(
        community_server_id=community_server_id,
        user_discord_id=user_discord_id,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: str,
    user_discord_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RemoveCommunityAdminResponse]:
    """Remove Community Admin

     Remove admin status from a user in a specific community server.

    Sets CommunityMember.role = 'member'. Prevents removing the last admin to ensure
    the community always has at least one admin.

    Args:
        community_server_id: Discord guild ID
        user_discord_id: Discord ID of user to demote
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        RemoveCommunityAdminResponse: Operation result

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 409: Cannot remove last admin

    Args:
        community_server_id (str):
        user_discord_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RemoveCommunityAdminResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        user_discord_id=user_discord_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: str,
    user_discord_id: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RemoveCommunityAdminResponse | None:
    """Remove Community Admin

     Remove admin status from a user in a specific community server.

    Sets CommunityMember.role = 'member'. Prevents removing the last admin to ensure
    the community always has at least one admin.

    Args:
        community_server_id: Discord guild ID
        user_discord_id: Discord ID of user to demote
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        RemoveCommunityAdminResponse: Operation result

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 409: Cannot remove last admin

    Args:
        community_server_id (str):
        user_discord_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RemoveCommunityAdminResponse
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            user_discord_id=user_discord_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
