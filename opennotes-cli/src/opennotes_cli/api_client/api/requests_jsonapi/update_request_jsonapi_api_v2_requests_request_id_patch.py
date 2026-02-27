from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.request_single_response import RequestSingleResponse
from ...models.request_update_request import RequestUpdateRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    request_id: str,
    *,
    body: RequestUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v2/requests/{request_id}".format(
            request_id=quote(str(request_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | RequestSingleResponse | None:
    if response.status_code == 200:
        response_200 = RequestSingleResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | RequestSingleResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    request_id: str,
    *,
    client: AuthenticatedClient,
    body: RequestUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RequestSingleResponse]:
    """Update Request Jsonapi

     Update a request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):
        body (RequestUpdateRequest): JSON:API request body for updating a request.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RequestSingleResponse]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    request_id: str,
    *,
    client: AuthenticatedClient,
    body: RequestUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RequestSingleResponse | None:
    """Update Request Jsonapi

     Update a request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):
        body (RequestUpdateRequest): JSON:API request body for updating a request.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RequestSingleResponse
    """

    return sync_detailed(
        request_id=request_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    request_id: str,
    *,
    client: AuthenticatedClient,
    body: RequestUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | RequestSingleResponse]:
    """Update Request Jsonapi

     Update a request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):
        body (RequestUpdateRequest): JSON:API request body for updating a request.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | RequestSingleResponse]
    """

    kwargs = _get_kwargs(
        request_id=request_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    request_id: str,
    *,
    client: AuthenticatedClient,
    body: RequestUpdateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | RequestSingleResponse | None:
    """Update Request Jsonapi

     Update a request with JSON:API format.

    JSON:API 1.1 requires:
    - Request body with 'data' object containing 'type', 'id', and 'attributes'
    - The 'id' in the body must match the URL parameter
    - Response with 200 OK status
    - Response body with 'data' object containing updated resource

    Returns JSON:API formatted response with data and jsonapi keys.

    Args:
        request_id (str):
        x_api_key (None | str | Unset):
        body (RequestUpdateRequest): JSON:API request body for updating a request.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | RequestSingleResponse
    """

    return (
        await asyncio_detailed(
            request_id=request_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
