from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.claim_relevance_check_request import ClaimRelevanceCheckRequest
from ...models.claim_relevance_check_response import ClaimRelevanceCheckResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ClaimRelevanceCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/claim-relevance-checks",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | ClaimRelevanceCheckResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ClaimRelevanceCheckResponse.from_dict(response.json())

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
) -> Response[Any | ClaimRelevanceCheckResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ClaimRelevanceCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ClaimRelevanceCheckResponse | HTTPValidationError]:
    """Create Claim Relevance Check

     Check if a fact-check match is relevant to a user's message.

    Uses LLM to determine whether the matched content addresses a specific
    verifiable claim in the original message. Returns an outcome and reasoning.

    Fail-open semantics: if the LLM is unavailable, returns indeterminate
    with should_flag=true so legitimate matches are never silently dropped.

    JSON:API 1.1 action endpoint.

    Args:
        x_api_key (None | str | Unset):
        body (ClaimRelevanceCheckRequest): JSON:API request body for performing a claim relevance
            check.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClaimRelevanceCheckResponse | HTTPValidationError]
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
    body: ClaimRelevanceCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ClaimRelevanceCheckResponse | HTTPValidationError | None:
    """Create Claim Relevance Check

     Check if a fact-check match is relevant to a user's message.

    Uses LLM to determine whether the matched content addresses a specific
    verifiable claim in the original message. Returns an outcome and reasoning.

    Fail-open semantics: if the LLM is unavailable, returns indeterminate
    with should_flag=true so legitimate matches are never silently dropped.

    JSON:API 1.1 action endpoint.

    Args:
        x_api_key (None | str | Unset):
        body (ClaimRelevanceCheckRequest): JSON:API request body for performing a claim relevance
            check.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClaimRelevanceCheckResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ClaimRelevanceCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | ClaimRelevanceCheckResponse | HTTPValidationError]:
    """Create Claim Relevance Check

     Check if a fact-check match is relevant to a user's message.

    Uses LLM to determine whether the matched content addresses a specific
    verifiable claim in the original message. Returns an outcome and reasoning.

    Fail-open semantics: if the LLM is unavailable, returns indeterminate
    with should_flag=true so legitimate matches are never silently dropped.

    JSON:API 1.1 action endpoint.

    Args:
        x_api_key (None | str | Unset):
        body (ClaimRelevanceCheckRequest): JSON:API request body for performing a claim relevance
            check.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | ClaimRelevanceCheckResponse | HTTPValidationError]
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
    body: ClaimRelevanceCheckRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | ClaimRelevanceCheckResponse | HTTPValidationError | None:
    """Create Claim Relevance Check

     Check if a fact-check match is relevant to a user's message.

    Uses LLM to determine whether the matched content addresses a specific
    verifiable claim in the original message. Returns an outcome and reasoning.

    Fail-open semantics: if the LLM is unavailable, returns indeterminate
    with should_flag=true so legitimate matches are never silently dropped.

    JSON:API 1.1 action endpoint.

    Args:
        x_api_key (None | str | Unset):
        body (ClaimRelevanceCheckRequest): JSON:API request body for performing a claim relevance
            check.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | ClaimRelevanceCheckResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
