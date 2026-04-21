from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.moderation_action_create import ModerationActionCreate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ModerationActionCreate,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/public/v1/moderation-actions",
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
    *,
    client: AuthenticatedClient,
    body: ModerationActionCreate,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Create Moderation Action Endpoint

     Create a moderation action in PROPOSED state.

    Publishes a moderation_action.proposed NATS event after successful creation.

    Args:
        x_api_key (None | str | Unset):
        body (ModerationActionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
    body: ModerationActionCreate,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Create Moderation Action Endpoint

     Create a moderation action in PROPOSED state.

    Publishes a moderation_action.proposed NATS event after successful creation.

    Args:
        x_api_key (None | str | Unset):
        body (ModerationActionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ModerationActionCreate,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Create Moderation Action Endpoint

     Create a moderation action in PROPOSED state.

    Publishes a moderation_action.proposed NATS event after successful creation.

    Args:
        x_api_key (None | str | Unset):
        body (ModerationActionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
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
    body: ModerationActionCreate,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Create Moderation Action Endpoint

     Create a moderation action in PROPOSED state.

    Publishes a moderation_action.proposed NATS event after successful creation.

    Args:
        x_api_key (None | str | Unset):
        body (ModerationActionCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
