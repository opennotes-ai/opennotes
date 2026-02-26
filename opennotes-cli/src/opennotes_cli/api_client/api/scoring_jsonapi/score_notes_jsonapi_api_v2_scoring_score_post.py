from http import HTTPStatus
from typing import Any, cast

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.scoring_result_response import ScoringResultResponse
from ...models.scoring_run_request import ScoringRunRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    body: ScoringRunRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/scoring/score",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | ScoringResultResponse | None:
    if response.status_code == 200:
        response_200 = ScoringResultResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | ScoringResultResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ScoringRunRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoringResultResponse]:
    r"""Score Notes Jsonapi

     Score notes using the external scoring adapter in JSON:API format.

    This endpoint runs the Community Notes scoring algorithm on the provided
    notes, ratings, and enrollment data.

    JSON:API request body must contain:
    - data.type: \"scoring-requests\"
    - data.attributes.notes: List of notes to score
    - data.attributes.ratings: List of ratings for the notes
    - data.attributes.enrollment: List of user enrollment data
    - data.attributes.status: Optional note status history

    Returns JSON:API formatted response with scored_notes, helpful_scores,
    and auxiliary_info.

    Args:
        x_api_key (None | str | Unset):
        body (ScoringRunRequest): JSON:API request body for scoring run.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoringResultResponse]
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
    body: ScoringRunRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoringResultResponse | None:
    r"""Score Notes Jsonapi

     Score notes using the external scoring adapter in JSON:API format.

    This endpoint runs the Community Notes scoring algorithm on the provided
    notes, ratings, and enrollment data.

    JSON:API request body must contain:
    - data.type: \"scoring-requests\"
    - data.attributes.notes: List of notes to score
    - data.attributes.ratings: List of ratings for the notes
    - data.attributes.enrollment: List of user enrollment data
    - data.attributes.status: Optional note status history

    Returns JSON:API formatted response with scored_notes, helpful_scores,
    and auxiliary_info.

    Args:
        x_api_key (None | str | Unset):
        body (ScoringRunRequest): JSON:API request body for scoring run.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoringResultResponse
    """

    return sync_detailed(
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ScoringRunRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | ScoringResultResponse]:
    r"""Score Notes Jsonapi

     Score notes using the external scoring adapter in JSON:API format.

    This endpoint runs the Community Notes scoring algorithm on the provided
    notes, ratings, and enrollment data.

    JSON:API request body must contain:
    - data.type: \"scoring-requests\"
    - data.attributes.notes: List of notes to score
    - data.attributes.ratings: List of ratings for the notes
    - data.attributes.enrollment: List of user enrollment data
    - data.attributes.status: Optional note status history

    Returns JSON:API formatted response with scored_notes, helpful_scores,
    and auxiliary_info.

    Args:
        x_api_key (None | str | Unset):
        body (ScoringRunRequest): JSON:API request body for scoring run.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | ScoringResultResponse]
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
    body: ScoringRunRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | ScoringResultResponse | None:
    r"""Score Notes Jsonapi

     Score notes using the external scoring adapter in JSON:API format.

    This endpoint runs the Community Notes scoring algorithm on the provided
    notes, ratings, and enrollment data.

    JSON:API request body must contain:
    - data.type: \"scoring-requests\"
    - data.attributes.notes: List of notes to score
    - data.attributes.ratings: List of ratings for the notes
    - data.attributes.enrollment: List of user enrollment data
    - data.attributes.status: Optional note status history

    Returns JSON:API formatted response with scored_notes, helpful_scores,
    and auxiliary_info.

    Args:
        x_api_key (None | str | Unset):
        body (ScoringRunRequest): JSON:API request body for scoring run.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | ScoringResultResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
