from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.candidate_single_response import CandidateSingleResponse
from ...models.http_validation_error import HTTPValidationError
from ...models.set_rating_request import SetRatingRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    candidate_id: UUID,
    *,
    body: SetRatingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v1/fact-checking/candidates/{candidate_id}/rating".format(
            candidate_id=quote(str(candidate_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | CandidateSingleResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = CandidateSingleResponse.from_dict(response.json())

        return response_200

    if response.status_code == 401:
        response_401 = cast(Any, None)
        return response_401

    if response.status_code == 404:
        response_404 = cast(Any, None)
        return response_404

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | CandidateSingleResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    candidate_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SetRatingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CandidateSingleResponse | HTTPValidationError]:
    """Set Rating Jsonapi

     Set rating for a specific candidate.

    Sets the human-approved rating on a candidate. Optionally triggers
    promotion if the candidate is ready (has content and rating).

    Args:
        candidate_id: UUID of the candidate to update.
        body: JSON:API request with rating attributes.

    Returns:
        JSON:API response with updated candidate resource.

    Args:
        candidate_id (UUID):
        x_api_key (None | str | Unset):
        body (SetRatingRequest): JSON:API request body for setting rating on a candidate.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CandidateSingleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        candidate_id=candidate_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    candidate_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SetRatingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CandidateSingleResponse | HTTPValidationError | None:
    """Set Rating Jsonapi

     Set rating for a specific candidate.

    Sets the human-approved rating on a candidate. Optionally triggers
    promotion if the candidate is ready (has content and rating).

    Args:
        candidate_id: UUID of the candidate to update.
        body: JSON:API request with rating attributes.

    Returns:
        JSON:API response with updated candidate resource.

    Args:
        candidate_id (UUID):
        x_api_key (None | str | Unset):
        body (SetRatingRequest): JSON:API request body for setting rating on a candidate.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CandidateSingleResponse | HTTPValidationError
    """

    return sync_detailed(
        candidate_id=candidate_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    candidate_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SetRatingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | CandidateSingleResponse | HTTPValidationError]:
    """Set Rating Jsonapi

     Set rating for a specific candidate.

    Sets the human-approved rating on a candidate. Optionally triggers
    promotion if the candidate is ready (has content and rating).

    Args:
        candidate_id: UUID of the candidate to update.
        body: JSON:API request with rating attributes.

    Returns:
        JSON:API response with updated candidate resource.

    Args:
        candidate_id (UUID):
        x_api_key (None | str | Unset):
        body (SetRatingRequest): JSON:API request body for setting rating on a candidate.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | CandidateSingleResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        candidate_id=candidate_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    candidate_id: UUID,
    *,
    client: AuthenticatedClient,
    body: SetRatingRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | CandidateSingleResponse | HTTPValidationError | None:
    """Set Rating Jsonapi

     Set rating for a specific candidate.

    Sets the human-approved rating on a candidate. Optionally triggers
    promotion if the candidate is ready (has content and rating).

    Args:
        candidate_id: UUID of the candidate to update.
        body: JSON:API request with rating attributes.

    Returns:
        JSON:API response with updated candidate resource.

    Args:
        candidate_id (UUID):
        x_api_key (None | str | Unset):
        body (SetRatingRequest): JSON:API request body for setting rating on a candidate.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | CandidateSingleResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            candidate_id=candidate_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
