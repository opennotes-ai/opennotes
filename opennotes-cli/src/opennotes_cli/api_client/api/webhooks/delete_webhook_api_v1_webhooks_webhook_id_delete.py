from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delete_webhook_api_v1_webhooks_webhook_id_delete_response_delete_webhook_api_v1_webhooks_webhook_id_delete import (
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    webhook_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/webhooks/{webhook_id}".format(
            webhook_id=quote(str(webhook_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete.from_dict(
            response.json()
        )

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
) -> Response[
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    webhook_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
]:
    """Delete Webhook

    Args:
        webhook_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        webhook_id=webhook_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    webhook_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> (
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
    | None
):
    """Delete Webhook

    Args:
        webhook_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete | HTTPValidationError
    """

    return sync_detailed(
        webhook_id=webhook_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    webhook_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
]:
    """Delete Webhook

    Args:
        webhook_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        webhook_id=webhook_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    webhook_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> (
    DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete
    | HTTPValidationError
    | None
):
    """Delete Webhook

    Args:
        webhook_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeleteWebhookApiV1WebhooksWebhookIdDeleteResponseDeleteWebhookApiV1WebhooksWebhookIdDelete | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            webhook_id=webhook_id,
            client=client,
        )
    ).parsed
