from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    url_query: None | str | Unset = UNSET,
    job_id: None | str | Unset = UNSET,
    generate: bool | Unset = False,
    source_type: str | Unset = "url",
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    params: dict[str, Any] = {}

    json_url_query: None | str | Unset
    if isinstance(url_query, Unset):
        json_url_query = UNSET
    else:
        json_url_query = url_query
    params["url"] = json_url_query

    json_job_id: None | str | Unset
    if isinstance(job_id, Unset):
        json_job_id = UNSET
    else:
        json_job_id = job_id
    params["job_id"] = json_job_id

    params["generate"] = generate

    params["source_type"] = source_type

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v1/url_scan/archive-preview",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | str | None:
    if response.status_code == 200:
        response_200 = response.text
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
) -> Response[HTTPValidationError | str]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    url_query: None | str | Unset = UNSET,
    job_id: None | str | Unset = UNSET,
    generate: bool | Unset = False,
    source_type: str | Unset = "url",
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | str]:
    """Archive Preview Route

    Args:
        url_query (None | str | Unset):
        job_id (None | str | Unset):
        generate (bool | Unset):  Default: False.
        source_type (str | Unset):  Default: 'url'.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | str]
    """

    kwargs = _get_kwargs(
        url_query=url_query,
        job_id=job_id,
        generate=generate,
        source_type=source_type,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    url_query: None | str | Unset = UNSET,
    job_id: None | str | Unset = UNSET,
    generate: bool | Unset = False,
    source_type: str | Unset = "url",
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | str | None:
    """Archive Preview Route

    Args:
        url_query (None | str | Unset):
        job_id (None | str | Unset):
        generate (bool | Unset):  Default: False.
        source_type (str | Unset):  Default: 'url'.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | str
    """

    return sync_detailed(
        client=client,
        url_query=url_query,
        job_id=job_id,
        generate=generate,
        source_type=source_type,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    url_query: None | str | Unset = UNSET,
    job_id: None | str | Unset = UNSET,
    generate: bool | Unset = False,
    source_type: str | Unset = "url",
    x_api_key: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | str]:
    """Archive Preview Route

    Args:
        url_query (None | str | Unset):
        job_id (None | str | Unset):
        generate (bool | Unset):  Default: False.
        source_type (str | Unset):  Default: 'url'.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | str]
    """

    kwargs = _get_kwargs(
        url_query=url_query,
        job_id=job_id,
        generate=generate,
        source_type=source_type,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    url_query: None | str | Unset = UNSET,
    job_id: None | str | Unset = UNSET,
    generate: bool | Unset = False,
    source_type: str | Unset = "url",
    x_api_key: None | str | Unset = UNSET,
) -> HTTPValidationError | str | None:
    """Archive Preview Route

    Args:
        url_query (None | str | Unset):
        job_id (None | str | Unset):
        generate (bool | Unset):  Default: False.
        source_type (str | Unset):  Default: 'url'.
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | str
    """

    return (
        await asyncio_detailed(
            client=client,
            url_query=url_query,
            job_id=job_id,
            generate=generate,
            source_type=source_type,
            x_api_key=x_api_key,
        )
    ).parsed
