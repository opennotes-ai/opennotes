from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.orchestrator_single_response import OrchestratorSingleResponse
from ...models.orchestrator_update_request import OrchestratorUpdateRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    orchestrator_id: UUID,
    *,
    body: OrchestratorUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v2/simulation-orchestrators/{orchestrator_id}".format(
            orchestrator_id=quote(str(orchestrator_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OrchestratorSingleResponse | None:
    if response.status_code == 200:
        response_200 = OrchestratorSingleResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | OrchestratorSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    orchestrator_id: UUID,
    *,
    client: AuthenticatedClient,
    body: OrchestratorUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OrchestratorSingleResponse]:
    """Update Orchestrator Jsonapi

    Args:
        orchestrator_id (UUID):
        x_api_key (None | str | Unset):
        body (OrchestratorUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrchestratorSingleResponse]
    """

    kwargs = _get_kwargs(
        orchestrator_id=orchestrator_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    orchestrator_id: UUID,
    *,
    client: AuthenticatedClient,
    body: OrchestratorUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | OrchestratorSingleResponse | None:
    """Update Orchestrator Jsonapi

    Args:
        orchestrator_id (UUID):
        x_api_key (None | str | Unset):
        body (OrchestratorUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrchestratorSingleResponse
    """

    return sync_detailed(
        orchestrator_id=orchestrator_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    orchestrator_id: UUID,
    *,
    client: AuthenticatedClient,
    body: OrchestratorUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OrchestratorSingleResponse]:
    """Update Orchestrator Jsonapi

    Args:
        orchestrator_id (UUID):
        x_api_key (None | str | Unset):
        body (OrchestratorUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OrchestratorSingleResponse]
    """

    kwargs = _get_kwargs(
        orchestrator_id=orchestrator_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    orchestrator_id: UUID,
    *,
    client: AuthenticatedClient,
    body: OrchestratorUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | OrchestratorSingleResponse | None:
    """Update Orchestrator Jsonapi

    Args:
        orchestrator_id (UUID):
        x_api_key (None | str | Unset):
        body (OrchestratorUpdateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OrchestratorSingleResponse
    """

    return (
        await asyncio_detailed(
            orchestrator_id=orchestrator_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
