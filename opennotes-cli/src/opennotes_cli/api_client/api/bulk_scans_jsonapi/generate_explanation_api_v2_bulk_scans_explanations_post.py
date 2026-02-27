from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.explanation_create_request import ExplanationCreateRequest
from ...models.explanation_result_response import ExplanationResultResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ExplanationCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/bulk-scans/explanations",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ExplanationResultResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ExplanationResultResponse.from_dict(response.json())

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
) -> Response[Any | ExplanationResultResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ExplanationCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ExplanationResultResponse | HTTPValidationError]:
    r"""Generate Explanation

     Generate an AI explanation for why a message was flagged.

    JSON:API request body must contain:
    - data.type: \"scan-explanations\"
    - data.attributes.original_message: The flagged message content
    - data.attributes.fact_check_item_id: UUID of the matched fact-check item
    - data.attributes.community_server_id: Community server UUID for context

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a scan-explanations resource with the generated explanation.

    Args:
        x_api_key (None | str | Unset):
        body (ExplanationCreateRequest): JSON:API request body for generating a scan explanation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ExplanationResultResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: ExplanationCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ExplanationResultResponse | HTTPValidationError | None:
    r"""Generate Explanation

     Generate an AI explanation for why a message was flagged.

    JSON:API request body must contain:
    - data.type: \"scan-explanations\"
    - data.attributes.original_message: The flagged message content
    - data.attributes.fact_check_item_id: UUID of the matched fact-check item
    - data.attributes.community_server_id: Community server UUID for context

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a scan-explanations resource with the generated explanation.

    Args:
        x_api_key (None | str | Unset):
        body (ExplanationCreateRequest): JSON:API request body for generating a scan explanation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ExplanationResultResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ExplanationCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ExplanationResultResponse | HTTPValidationError]:
    r"""Generate Explanation

     Generate an AI explanation for why a message was flagged.

    JSON:API request body must contain:
    - data.type: \"scan-explanations\"
    - data.attributes.original_message: The flagged message content
    - data.attributes.fact_check_item_id: UUID of the matched fact-check item
    - data.attributes.community_server_id: Community server UUID for context

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a scan-explanations resource with the generated explanation.

    Args:
        x_api_key (None | str | Unset):
        body (ExplanationCreateRequest): JSON:API request body for generating a scan explanation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ExplanationResultResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ExplanationCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ExplanationResultResponse | HTTPValidationError | None:
    r"""Generate Explanation

     Generate an AI explanation for why a message was flagged.

    JSON:API request body must contain:
    - data.type: \"scan-explanations\"
    - data.attributes.original_message: The flagged message content
    - data.attributes.fact_check_item_id: UUID of the matched fact-check item
    - data.attributes.community_server_id: Community server UUID for context

    Authorization: Requires admin access to the specified community.
    Service accounts have unrestricted access.

    Returns a scan-explanations resource with the generated explanation.

    Args:
        x_api_key (None | str | Unset):
        body (ExplanationCreateRequest): JSON:API request body for generating a scan explanation.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ExplanationResultResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
