from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: str,
    *,
    config_key: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_config_key: None | str | Unset
    if isinstance(config_key, Unset):
        json_config_key = UNSET
    else:
        json_config_key = config_key
    params["config_key"] = json_config_key

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/community-config/{community_server_id}".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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
) -> Response[Any | HTTPValidationError]:
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
    config_key: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Reset Community Config

     Reset community server configuration to defaults.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If config_key is provided, only that specific
    key is deleted. If config_key is None, all configuration for the community server
    is deleted.

    Requires: User must be an admin or moderator of the community server.

    Args:
        community_server_id (str):
        config_key (None | str | Unset): Specific config key to reset (leave empty to reset all)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        config_key=config_key,
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
    config_key: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Reset Community Config

     Reset community server configuration to defaults.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If config_key is provided, only that specific
    key is deleted. If config_key is None, all configuration for the community server
    is deleted.

    Requires: User must be an admin or moderator of the community server.

    Args:
        community_server_id (str):
        config_key (None | str | Unset): Specific config key to reset (leave empty to reset all)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        config_key=config_key,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    config_key: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Reset Community Config

     Reset community server configuration to defaults.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If config_key is provided, only that specific
    key is deleted. If config_key is None, all configuration for the community server
    is deleted.

    Requires: User must be an admin or moderator of the community server.

    Args:
        community_server_id (str):
        config_key (None | str | Unset): Specific config key to reset (leave empty to reset all)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        config_key=config_key,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: str,
    *,
    client: AuthenticatedClient,
    config_key: None | str | Unset = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Reset Community Config

     Reset community server configuration to defaults.

    Accepts a platform-specific community ID (e.g., Discord guild ID) and looks up
    the corresponding community server. If config_key is provided, only that specific
    key is deleted. If config_key is None, all configuration for the community server
    is deleted.

    Requires: User must be an admin or moderator of the community server.

    Args:
        community_server_id (str):
        config_key (None | str | Unset): Specific config key to reset (leave empty to reset all)
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            config_key=config_key,
            x_api_key=x_api_key,
        )
    ).parsed
