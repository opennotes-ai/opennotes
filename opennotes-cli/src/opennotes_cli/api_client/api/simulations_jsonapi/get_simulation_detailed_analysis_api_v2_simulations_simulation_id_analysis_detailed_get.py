from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.detailed_analysis_response import DetailedAnalysisResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    simulation_id: UUID,
    *,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["page[number]"] = pagenumber

    params["page[size]"] = pagesize

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/simulations/{simulation_id}/analysis/detailed".format(
            simulation_id=quote(str(simulation_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DetailedAnalysisResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DetailedAnalysisResponse.from_dict(response.json())

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
) -> Response[DetailedAnalysisResponse | HTTPValidationError]:
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
    x_api_key: None | str | Unset = UNSET,
) -> Response[DetailedAnalysisResponse | HTTPValidationError]:
    """Get Simulation Detailed Analysis

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DetailedAnalysisResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagenumber=pagenumber,
        pagesize=pagesize,
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
    x_api_key: None | str | Unset = UNSET,
) -> DetailedAnalysisResponse | HTTPValidationError | None:
    """Get Simulation Detailed Analysis

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DetailedAnalysisResponse | HTTPValidationError
    """

    return sync_detailed(
        simulation_id=simulation_id,
        client=client,
        pagenumber=pagenumber,
        pagesize=pagesize,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    simulation_id: UUID,
    *,
    client: AuthenticatedClient,
    pagenumber: int | Unset = 1,
    pagesize: int | Unset = 20,
    x_api_key: None | str | Unset = UNSET,
) -> Response[DetailedAnalysisResponse | HTTPValidationError]:
    """Get Simulation Detailed Analysis

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DetailedAnalysisResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        simulation_id=simulation_id,
        pagenumber=pagenumber,
        pagesize=pagesize,
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
    x_api_key: None | str | Unset = UNSET,
) -> DetailedAnalysisResponse | HTTPValidationError | None:
    """Get Simulation Detailed Analysis

    Args:
        simulation_id (UUID):
        pagenumber (int | Unset):  Default: 1.
        pagesize (int | Unset):  Default: 20.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DetailedAnalysisResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            simulation_id=simulation_id,
            client=client,
            pagenumber=pagenumber,
            pagesize=pagesize,
            x_api_key=x_api_key,
        )
    ).parsed
