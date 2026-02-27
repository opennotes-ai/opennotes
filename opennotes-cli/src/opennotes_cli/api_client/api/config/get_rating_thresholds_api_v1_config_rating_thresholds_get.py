from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rating_thresholds_response import RatingThresholdsResponse
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
        "url": "/api/v1/config/rating-thresholds",
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RatingThresholdsResponse | None:
    if response.status_code == 200:
        response_200 = RatingThresholdsResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RatingThresholdsResponse]:
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
) -> Response[Any | HTTPValidationError | RatingThresholdsResponse]:
    """Get Rating Thresholds

     Get rating threshold configuration values.

    These values define the minimum number of ratings and unique raters required
    before a note can receive CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL status.

    The thresholds should match the Community Notes scoring algorithm defaults.

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RatingThresholdsResponse]
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
) -> Any | HTTPValidationError | RatingThresholdsResponse | None:
    """Get Rating Thresholds

     Get rating threshold configuration values.

    These values define the minimum number of ratings and unique raters required
    before a note can receive CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL status.

    The thresholds should match the Community Notes scoring algorithm defaults.

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RatingThresholdsResponse
    """

    return sync_detailed(
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RatingThresholdsResponse]:
    """Get Rating Thresholds

     Get rating threshold configuration values.

    These values define the minimum number of ratings and unique raters required
    before a note can receive CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL status.

    The thresholds should match the Community Notes scoring algorithm defaults.

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RatingThresholdsResponse]
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
) -> Any | HTTPValidationError | RatingThresholdsResponse | None:
    """Get Rating Thresholds

     Get rating threshold configuration values.

    These values define the minimum number of ratings and unique raters required
    before a note can receive CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL status.

    The thresholds should match the Community Notes scoring algorithm defaults.

    Args:
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RatingThresholdsResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
