from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.previously_seen_check_request import PreviouslySeenCheckRequest
from ...models.previously_seen_check_result_response import (
    PreviouslySeenCheckResultResponse,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: PreviouslySeenCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/previously-seen-messages/check",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | PreviouslySeenCheckResultResponse | None:
    if response.status_code == 200:
        response_200 = PreviouslySeenCheckResultResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | PreviouslySeenCheckResultResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: PreviouslySeenCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | PreviouslySeenCheckResultResponse]:
    """Check Previously Seen Jsonapi

     Check if a message has been seen before with JSON:API format.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    JSON:API 1.1 action endpoint that returns check results.

    Args:
        x_api_key (None | str | Unset):
        body (PreviouslySeenCheckRequest): JSON:API request body for checking previously seen
            messages.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PreviouslySeenCheckResultResponse]
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
    body: PreviouslySeenCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | PreviouslySeenCheckResultResponse | None:
    """Check Previously Seen Jsonapi

     Check if a message has been seen before with JSON:API format.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    JSON:API 1.1 action endpoint that returns check results.

    Args:
        x_api_key (None | str | Unset):
        body (PreviouslySeenCheckRequest): JSON:API request body for checking previously seen
            messages.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PreviouslySeenCheckResultResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PreviouslySeenCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | PreviouslySeenCheckResultResponse]:
    """Check Previously Seen Jsonapi

     Check if a message has been seen before with JSON:API format.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    JSON:API 1.1 action endpoint that returns check results.

    Args:
        x_api_key (None | str | Unset):
        body (PreviouslySeenCheckRequest): JSON:API request body for checking previously seen
            messages.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | PreviouslySeenCheckResultResponse]
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
    body: PreviouslySeenCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | PreviouslySeenCheckResultResponse | None:
    """Check Previously Seen Jsonapi

     Check if a message has been seen before with JSON:API format.

    This endpoint:
    1. Generates an embedding for the message text
    2. Searches for similar previously seen messages
    3. Resolves thresholds (channel override or global config)
    4. Returns action recommendations (auto-publish/auto-request)

    JSON:API 1.1 action endpoint that returns check results.

    Args:
        x_api_key (None | str | Unset):
        body (PreviouslySeenCheckRequest): JSON:API request body for checking previously seen
            messages.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | PreviouslySeenCheckResultResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
