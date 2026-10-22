from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.screenshot_response import ScreenshotResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    url_query: str,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    params["url"] = url_query

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/url_scan/screenshot",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ScreenshotResponse | None:
    if response.status_code == 200:
        response_200 = ScreenshotResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ScreenshotResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    url_query: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ScreenshotResponse]:
    """Screenshot Route

    Args:
        url_query (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ScreenshotResponse]
    """

    kwargs = _get_kwargs(
        url_query=url_query,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    url_query: str,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | ScreenshotResponse | None:
    """Screenshot Route

    Args:
        url_query (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ScreenshotResponse
    """

    return sync_detailed(
        client=client,
        url_query=url_query,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    url_query: str,
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | ScreenshotResponse]:
    """Screenshot Route

    Args:
        url_query (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ScreenshotResponse]
    """

    kwargs = _get_kwargs(
        url_query=url_query,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    url_query: str,
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | ScreenshotResponse | None:
    """Screenshot Route

    Args:
        url_query (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ScreenshotResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            url_query=url_query,
            x_api_key=x_api_key,
        )
    ).parsed
