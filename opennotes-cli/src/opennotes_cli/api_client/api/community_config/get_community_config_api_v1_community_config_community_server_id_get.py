from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.community_config_response import CommunityConfigResponse
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
        "url": "/api/v1/community-config/{community_server_id}".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CommunityConfigResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CommunityConfigResponse.from_dict(response.json())

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
) -> Response[Any | CommunityConfigResponse | HTTPValidationError]:
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
) -> Response[Any | CommunityConfigResponse | HTTPValidationError]:
    """Get Community Config

     Get all configuration settings for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server.

    Returns a dictionary of config_key: config_value pairs for the community server.
    If no configuration exists, returns an empty dictionary.

    Requires: User must be a member of the community server.
    Service accounts can view all configs.

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityConfigResponse | HTTPValidationError]
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
) -> Any | CommunityConfigResponse | HTTPValidationError | None:
    """Get Community Config

     Get all configuration settings for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server.

    Returns a dictionary of config_key: config_value pairs for the community server.
    If no configuration exists, returns an empty dictionary.

    Requires: User must be a member of the community server.
    Service accounts can view all configs.

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityConfigResponse | HTTPValidationError
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
) -> Response[Any | CommunityConfigResponse | HTTPValidationError]:
    """Get Community Config

     Get all configuration settings for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server.

    Returns a dictionary of config_key: config_value pairs for the community server.
    If no configuration exists, returns an empty dictionary.

    Requires: User must be a member of the community server.
    Service accounts can view all configs.

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CommunityConfigResponse | HTTPValidationError]
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
) -> Any | CommunityConfigResponse | HTTPValidationError | None:
    """Get Community Config

     Get all configuration settings for a specific community server.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server.

    Returns a dictionary of config_key: config_value pairs for the community server.
    If no configuration exists, returns an empty dictionary.

    Requires: User must be a member of the community server.
    Service accounts can view all configs.

    Args:
        community_server_id (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CommunityConfigResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
