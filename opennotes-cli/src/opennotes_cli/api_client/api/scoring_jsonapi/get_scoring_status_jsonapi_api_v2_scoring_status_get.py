from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.scoring_status_jsonapi_response import ScoringStatusJSONAPIResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/scoring/status",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ScoringStatusJSONAPIResponse | None:
    if response.status_code == 200:
        response_200 = ScoringStatusJSONAPIResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | ScoringStatusJSONAPIResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoringStatusJSONAPIResponse]:
    """Get Scoring Status Jsonapi

     Get system scoring status in JSON:API format.

    Returns a singleton resource with current scoring system status including:
    - Current note count
    - Active scoring tier
    - Data confidence level
    - Tier thresholds
    - Next tier upgrade information
    - Performance metrics
    - Warnings

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoringStatusJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoringStatusJSONAPIResponse | None:
    """Get Scoring Status Jsonapi

     Get system scoring status in JSON:API format.

    Returns a singleton resource with current scoring system status including:
    - Current note count
    - Active scoring tier
    - Data confidence level
    - Tier thresholds
    - Next tier upgrade information
    - Performance metrics
    - Warnings

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoringStatusJSONAPIResponse
    """

    return sync_detailed(
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoringStatusJSONAPIResponse]:
    """Get Scoring Status Jsonapi

     Get system scoring status in JSON:API format.

    Returns a singleton resource with current scoring system status including:
    - Current note count
    - Active scoring tier
    - Data confidence level
    - Tier thresholds
    - Next tier upgrade information
    - Performance metrics
    - Warnings

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoringStatusJSONAPIResponse]
    """

    kwargs = _get_kwargs(
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoringStatusJSONAPIResponse | None:
    """Get Scoring Status Jsonapi

     Get system scoring status in JSON:API format.

    Returns a singleton resource with current scoring system status including:
    - Current note count
    - Active scoring tier
    - Data confidence level
    - Tier thresholds
    - Next tier upgrade information
    - Performance metrics
    - Warnings

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoringStatusJSONAPIResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
