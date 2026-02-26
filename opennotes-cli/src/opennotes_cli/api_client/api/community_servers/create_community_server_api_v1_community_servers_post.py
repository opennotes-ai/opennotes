from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_server_create_request import CommunityServerCreateRequest
from ...models.community_server_create_response import CommunityServerCreateResponse
from ...models.create_community_server_api_v1_community_servers_post_response_401 import (
    CreateCommunityServerApiV1CommunityServersPostResponse401,
)
from ...models.create_community_server_api_v1_community_servers_post_response_403 import (
    CreateCommunityServerApiV1CommunityServersPostResponse403,
)
from ...models.create_community_server_api_v1_community_servers_post_response_409 import (
    CreateCommunityServerApiV1CommunityServersPostResponse409,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: CommunityServerCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/community-servers",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
    | None
):
    if response.status_code == 201:
        response_201 = CommunityServerCreateResponse.from_dict(response.json())

        return response_201

    if response.status_code == 401:
        response_401 = (
            CreateCommunityServerApiV1CommunityServersPostResponse401.from_dict(
                response.json()
            )
        )

        return response_401

    if response.status_code == 403:
        response_403 = (
            CreateCommunityServerApiV1CommunityServersPostResponse403.from_dict(
                response.json()
            )
        )

        return response_403

    if response.status_code == 409:
        response_409 = (
            CreateCommunityServerApiV1CommunityServersPostResponse409.from_dict(
                response.json()
            )
        )

        return response_409

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: CommunityServerCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
]:
    """Create Community Server

    Args:
        x_api_key (None | str | Unset):
        body (CommunityServerCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CommunityServerCreateResponse | CreateCommunityServerApiV1CommunityServersPostResponse401 | CreateCommunityServerApiV1CommunityServersPostResponse403 | CreateCommunityServerApiV1CommunityServersPostResponse409 | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: CommunityServerCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> (
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
    | None
):
    """Create Community Server

    Args:
        x_api_key (None | str | Unset):
        body (CommunityServerCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CommunityServerCreateResponse | CreateCommunityServerApiV1CommunityServersPostResponse401 | CreateCommunityServerApiV1CommunityServersPostResponse403 | CreateCommunityServerApiV1CommunityServersPostResponse409 | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CommunityServerCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
]:
    """Create Community Server

    Args:
        x_api_key (None | str | Unset):
        body (CommunityServerCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CommunityServerCreateResponse | CreateCommunityServerApiV1CommunityServersPostResponse401 | CreateCommunityServerApiV1CommunityServersPostResponse403 | CreateCommunityServerApiV1CommunityServersPostResponse409 | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: CommunityServerCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> (
    CommunityServerCreateResponse
    | CreateCommunityServerApiV1CommunityServersPostResponse401
    | CreateCommunityServerApiV1CommunityServersPostResponse403
    | CreateCommunityServerApiV1CommunityServersPostResponse409
    | HTTPValidationError
    | None
):
    """Create Community Server

    Args:
        x_api_key (None | str | Unset):
        body (CommunityServerCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CommunityServerCreateResponse | CreateCommunityServerApiV1CommunityServersPostResponse401 | CreateCommunityServerApiV1CommunityServersPostResponse403 | CreateCommunityServerApiV1CommunityServersPostResponse409 | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
