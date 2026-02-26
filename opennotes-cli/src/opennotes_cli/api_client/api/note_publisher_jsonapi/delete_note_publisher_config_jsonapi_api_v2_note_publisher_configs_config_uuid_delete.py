from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    config_uuid: UUID,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v2/note-publisher-configs/{config_uuid}".format(
            config_uuid=quote(str(config_uuid), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    config_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Delete Note Publisher Config Jsonapi

     Delete a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.

    Args:
        config_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        config_uuid=config_uuid,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    config_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Delete Note Publisher Config Jsonapi

     Delete a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.

    Args:
        config_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        config_uuid=config_uuid,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    config_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Delete Note Publisher Config Jsonapi

     Delete a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.

    Args:
        config_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        config_uuid=config_uuid,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    config_uuid: UUID,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Delete Note Publisher Config Jsonapi

     Delete a note publisher config with JSON:API format.

    JSON:API 1.1 requires:
    - Response with 204 No Content status on success
    - No response body on success
    - JSON:API error format for errors

    Returns 204 No Content on success, JSON:API error on failure.

    Args:
        config_uuid (UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            config_uuid=config_uuid,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
