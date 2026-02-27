from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.results_list_response import ResultsListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    simulation_id: UUID,
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    agent_instance_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["page[number]"] = pagenumber

    params["page[size]"] = pagesize

    json_agent_instance_id: None | str | Unset
    if isinstance(agent_instance_id, Unset):
        json_agent_instance_id = UNSET
    elif isinstance(agent_instance_id, UUID):
        json_agent_instance_id = str(agent_instance_id)
    else:
        json_agent_instance_id = agent_instance_id
    params["agent_instance_id"] = json_agent_instance_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/simulations/{simulation_id}/results".format(
            simulation_id=quote(str(simulation_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ResultsListResponse | None:
    if response.status_code == 200:
        response_200 = ResultsListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ResultsListResponse]:
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
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    agent_instance_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ResultsListResponse]:
    """Get Simulation Results

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        agent_instance_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResultsListResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagenumber=pagenumber,
        pagesize=pagesize,
        agent_instance_id=agent_instance_id,
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
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    agent_instance_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | ResultsListResponse | None:
    """Get Simulation Results

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        agent_instance_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResultsListResponse
    """

    return sync_detailed(
        simulation_id=simulation_id,
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        agent_instance_id=agent_instance_id,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    agent_instance_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ResultsListResponse]:
    """Get Simulation Results

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        agent_instance_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResultsListResponse]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagenumber=pagenumber,
        pagesize=pagesize,
        agent_instance_id=agent_instance_id,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    agent_instance_id: None | Unset | UUID = UNSET,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | ResultsListResponse | None:
    """Get Simulation Results

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        agent_instance_id (None | Unset | UUID):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResultsListResponse
    """

    return (
        await asyncio_detailed(
            simulation_id=simulation_id,
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            agent_instance_id=agent_instance_id,
            x_api_key=x_api_key,
        )
    ).parsed
