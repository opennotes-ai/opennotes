from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.note_requests_create_request import NoteRequestsCreateRequest
from ...models.note_requests_result_response import NoteRequestsResultResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    scan_id: UUID,
    *,
    body: NoteRequestsCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/bulk-scans/{scan_id}/note-requests".format(
            scan_id=quote(str(scan_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | NoteRequestsResultResponse | None:
    if response.status_code == 200:
        response_200 = NoteRequestsResultResponse.from_dict(response.json())

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
) -> Response[Any | HTTPValidationError | NoteRequestsResultResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    body: NoteRequestsCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteRequestsResultResponse]:
    r"""Create Note Requests

     Create note requests for selected flagged messages.

    JSON:API request body must contain:
    - data.type: \"note-requests\"
    - data.attributes.message_ids: List of message IDs from flagged results
    - data.attributes.generate_ai_notes: Whether to generate AI drafts

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Returns a note-request-batches resource with created count and IDs.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):
        body (NoteRequestsCreateRequest): JSON:API request body for creating note requests.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteRequestsResultResponse]
    """

    kwargs = _get_kwargs(
        scan_id=scan_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    body: NoteRequestsCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteRequestsResultResponse | None:
    r"""Create Note Requests

     Create note requests for selected flagged messages.

    JSON:API request body must contain:
    - data.type: \"note-requests\"
    - data.attributes.message_ids: List of message IDs from flagged results
    - data.attributes.generate_ai_notes: Whether to generate AI drafts

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Returns a note-request-batches resource with created count and IDs.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):
        body (NoteRequestsCreateRequest): JSON:API request body for creating note requests.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteRequestsResultResponse
    """

    return sync_detailed(
        scan_id=scan_id,
        client=client,
        body=body,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    body: NoteRequestsCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError | NoteRequestsResultResponse]:
    r"""Create Note Requests

     Create note requests for selected flagged messages.

    JSON:API request body must contain:
    - data.type: \"note-requests\"
    - data.attributes.message_ids: List of message IDs from flagged results
    - data.attributes.generate_ai_notes: Whether to generate AI drafts

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Returns a note-request-batches resource with created count and IDs.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):
        body (NoteRequestsCreateRequest): JSON:API request body for creating note requests.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError | NoteRequestsResultResponse]
    """

    kwargs = _get_kwargs(
        scan_id=scan_id,
        body=body,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    scan_id: UUID,
    *,
    client: AuthenticatedClient,
    body: NoteRequestsCreateRequest,
    x_api_key: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | NoteRequestsResultResponse | None:
    r"""Create Note Requests

     Create note requests for selected flagged messages.

    JSON:API request body must contain:
    - data.type: \"note-requests\"
    - data.attributes.message_ids: List of message IDs from flagged results
    - data.attributes.generate_ai_notes: Whether to generate AI drafts

    Authorization: User must be the scan initiator OR a community admin.
    Service accounts have unrestricted access.

    Returns a note-request-batches resource with created count and IDs.

    Args:
        scan_id (UUID):
        x_api_key (None | str | Unset):
        body (NoteRequestsCreateRequest): JSON:API request body for creating note requests.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError | NoteRequestsResultResponse
    """

    return (
        await asyncio_detailed(
            scan_id=scan_id,
            client=client,
            body=body,
            x_api_key=x_api_key,
        )
    ).parsed
