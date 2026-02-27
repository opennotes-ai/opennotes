from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.add_community_admin_request import AddCommunityAdminRequest
from ...models.community_admin_response import CommunityAdminResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: str,
    *,
    body: AddCommunityAdminRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/community-servers/{community_server_id}/admins".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CommunityAdminResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CommunityAdminResponse.from_dict(response.json())

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
) -> Response[Any | CommunityAdminResponse | HTTPValidationError]:
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
    body: AddCommunityAdminRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityAdminResponse | HTTPValidationError]:
    """Add Community Admin

     Add a user as admin for a specific community server.

    Sets CommunityMember.role = 'admin' for the specified user. Requires the requester
    to have existing admin privileges (service account, Open Notes admin, community admin,
    or Discord Manage Server permission).

    Args:
        community_server_id: Discord guild ID
        request_body: Request containing user_discord_id
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        CommunityAdminResponse: Updated community member information

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 400: Invalid input

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):
        body (AddCommunityAdminRequest): Request schema for adding a community admin.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityAdminResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        body=body,
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
    body: AddCommunityAdminRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityAdminResponse | HTTPValidationError | None:
    """Add Community Admin

     Add a user as admin for a specific community server.

    Sets CommunityMember.role = 'admin' for the specified user. Requires the requester
    to have existing admin privileges (service account, Open Notes admin, community admin,
    or Discord Manage Server permission).

    Args:
        community_server_id: Discord guild ID
        request_body: Request containing user_discord_id
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        CommunityAdminResponse: Updated community member information

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 400: Invalid input

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):
        body (AddCommunityAdminRequest): Request schema for adding a community admin.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityAdminResponse | HTTPValidationError
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: AddCommunityAdminRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CommunityAdminResponse | HTTPValidationError]:
    """Add Community Admin

     Add a user as admin for a specific community server.

    Sets CommunityMember.role = 'admin' for the specified user. Requires the requester
    to have existing admin privileges (service account, Open Notes admin, community admin,
    or Discord Manage Server permission).

    Args:
        community_server_id: Discord guild ID
        request_body: Request containing user_discord_id
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        CommunityAdminResponse: Updated community member information

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 400: Invalid input

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):
        body (AddCommunityAdminRequest): Request schema for adding a community admin.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityAdminResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    body: AddCommunityAdminRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CommunityAdminResponse | HTTPValidationError | None:
    """Add Community Admin

     Add a user as admin for a specific community server.

    Sets CommunityMember.role = 'admin' for the specified user. Requires the requester
    to have existing admin privileges (service account, Open Notes admin, community admin,
    or Discord Manage Server permission).

    Args:
        community_server_id: Discord guild ID
        request_body: Request containing user_discord_id
        db: Database session
        current_user: Current authenticated user
        http_request: FastAPI Request object

    Returns:
        CommunityAdminResponse: Updated community member information

    Raises:
        HTTPException 404: Community server or user not found
        HTTPException 403: Not authorized (not an admin)
        HTTPException 400: Invalid input

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):
        body (AddCommunityAdminRequest): Request schema for adding a community admin.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityAdminResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
