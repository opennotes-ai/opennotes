from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_simulation_timeline_api_v2_simulations_simulation_id_analysis_timeline_get_bucket_size import (
    GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.timeline_response import TimelineResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    simulation_id: UUID,
    *,
    bucket_size: GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize
    | Unset = GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_bucket_size: str | Unset = UNSET
    if not isinstance(bucket_size, Unset):
        json_bucket_size = bucket_size.value

    params["bucket_size"] = json_bucket_size

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/simulations/{simulation_id}/analysis/timeline".format(
            simulation_id=quote(str(simulation_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TimelineResponse | None:
    if response.status_code == 200:
        response_200 = TimelineResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | TimelineResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    bucket_size: GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize
    | Unset = GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TimelineResponse]:
    """Get Simulation Timeline

    Args:
        simulation_id (UUID):
        bucket_size
            (GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize | Unset):
            Default:
            GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TimelineResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        bucket_size=bucket_size,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    bucket_size: GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize
    | Unset = GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | TimelineResponse | None:
    """Get Simulation Timeline

    Args:
        simulation_id (UUID):
        bucket_size
            (GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize | Unset):
            Default:
            GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TimelineResponse
    """

    return sync_detailed(
        simulation_id=simulation_id,
        client=client,
        bucket_size=bucket_size,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    bucket_size: GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize
    | Unset = GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TimelineResponse]:
    """Get Simulation Timeline

    Args:
        simulation_id (UUID):
        bucket_size
            (GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize | Unset):
            Default:
            GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TimelineResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        bucket_size=bucket_size,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    bucket_size: GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize
    | Unset = GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | TimelineResponse | None:
    """Get Simulation Timeline

    Args:
        simulation_id (UUID):
        bucket_size
            (GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize | Unset):
            Default:
            GetSimulationTimelineApiV2SimulationsSimulationIdAnalysisTimelineGetBucketSize.AUTO.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TimelineResponse
    """

    return (
        await asyncio_detailed(
            simulation_id=simulation_id,
            client=client,
            bucket_size=bucket_size,
            x_api_key=x_api_key,
        )
    ).parsed
