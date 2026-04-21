from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.moderation_action_update import ModerationActionUpdate
from ...types import UNSET, Response, Unset


def _get_kwargs(
    action_id: UUID,
    *,
    body: ModerationActionUpdate,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/public/v1/moderation-actions/{action_id}".format(
            action_id=quote(str(action_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

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
    action_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ModerationActionUpdate,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Patch Moderation Action Endpoint

     Transition a moderation action to a new state.

    Validates the state transition against VALID_TRANSITIONS and returns 422
    on invalid transitions.  Publishes a NATS event for all target states
    except scan_exempt (plugin-initiated acknowledgement, no event needed).

    Args:
        action_id (UUID):
        x_api_key (None | str | Unset):
        body (ModerationActionUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        action_id=action_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    action_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ModerationActionUpdate,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Patch Moderation Action Endpoint

     Transition a moderation action to a new state.

    Validates the state transition against VALID_TRANSITIONS and returns 422
    on invalid transitions.  Publishes a NATS event for all target states
    except scan_exempt (plugin-initiated acknowledgement, no event needed).

    Args:
        action_id (UUID):
        x_api_key (None | str | Unset):
        body (ModerationActionUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        action_id=action_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    action_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ModerationActionUpdate,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Patch Moderation Action Endpoint

     Transition a moderation action to a new state.

    Validates the state transition against VALID_TRANSITIONS and returns 422
    on invalid transitions.  Publishes a NATS event for all target states
    except scan_exempt (plugin-initiated acknowledgement, no event needed).

    Args:
        action_id (UUID):
        x_api_key (None | str | Unset):
        body (ModerationActionUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        action_id=action_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    action_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ModerationActionUpdate,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Patch Moderation Action Endpoint

     Transition a moderation action to a new state.

    Validates the state transition against VALID_TRANSITIONS and returns 422
    on invalid transitions.  Publishes a NATS event for all target states
    except scan_exempt (plugin-initiated acknowledgement, no event needed).

    Args:
        action_id (UUID):
        x_api_key (None | str | Unset):
        body (ModerationActionUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            action_id=action_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
