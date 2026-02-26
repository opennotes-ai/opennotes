from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.llm_config_test_request import LLMConfigTestRequest
from ...models.llm_config_test_response import LLMConfigTestResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    community_server_id: UUID,
    *,
    body: LLMConfigTestRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/community-servers/{community_server_id}/llm-config/test".format(
            community_server_id=quote(str(community_server_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | LLMConfigTestResponse | None:
    if response.status_code == 200:
        response_200 = LLMConfigTestResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | LLMConfigTestResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: LLMConfigTestRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | LLMConfigTestResponse]:
    """Test Llm Config

     Test an LLM configuration without saving it.

    Validates the API key and checks connectivity.
    Requires admin or moderator access to the community server.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (LLMConfigTestRequest): Schema for testing an LLM configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | LLMConfigTestResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: LLMConfigTestRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | LLMConfigTestResponse | None:
    """Test Llm Config

     Test an LLM configuration without saving it.

    Validates the API key and checks connectivity.
    Requires admin or moderator access to the community server.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (LLMConfigTestRequest): Schema for testing an LLM configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | LLMConfigTestResponse
    """

    return sync_detailed(
        community_server_id=community_server_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: LLMConfigTestRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | LLMConfigTestResponse]:
    """Test Llm Config

     Test an LLM configuration without saving it.

    Validates the API key and checks connectivity.
    Requires admin or moderator access to the community server.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (LLMConfigTestRequest): Schema for testing an LLM configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | LLMConfigTestResponse]
    """

    kwargs = _get_kwargs(
        community_server_id=community_server_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    community_server_id: UUID,
    *,
    client: AuthenticatedClient,
    body: LLMConfigTestRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | LLMConfigTestResponse | None:
    """Test Llm Config

     Test an LLM configuration without saving it.

    Validates the API key and checks connectivity.
    Requires admin or moderator access to the community server.

    Args:
        community_server_id (UUID):
        x_api_key (None | str | Unset):
        body (LLMConfigTestRequest): Schema for testing an LLM configuration.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | LLMConfigTestResponse
    """

    return (
        await asyncio_detailed(
            community_server_id=community_server_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
