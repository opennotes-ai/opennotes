from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.playground_note_request_body import PlaygroundNoteRequestBody
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: UUID,
    *,
    body: PlaygroundNoteRequestBody,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/playgrounds/{community_server_id}/note-requests".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 201:
        response_201 = response.json()
        return response_201

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
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PlaygroundNoteRequestBody,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Create Playground Note Requests

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (PlaygroundNoteRequestBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PlaygroundNoteRequestBody,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Create Playground Note Requests

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (PlaygroundNoteRequestBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PlaygroundNoteRequestBody,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Create Playground Note Requests

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (PlaygroundNoteRequestBody):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PlaygroundNoteRequestBody,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Create Playground Note Requests

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (PlaygroundNoteRequestBody):

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
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
