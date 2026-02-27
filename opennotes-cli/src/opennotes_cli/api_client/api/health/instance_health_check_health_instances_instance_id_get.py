from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.instance_health_check_health_instances_instance_id_get_response_instance_health_check_health_instances_instance_id_get import (
    InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet,
)
from ...types import Response


def _get_kwargs(
    instance_id: str,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/health/instances/{instance_id}".format(
            instance_id=quote(str(instance_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
    | None
):
    if response.status_code == 200:
        response_200 = InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet.from_dict(
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
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    instance_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
]:
    """Instance Health Check

     Get health status of a specific instance.

    Args:
        instance_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet]
    """

    kwargs = _get_kwargs(
        instance_id=instance_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    instance_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
    | None
):
    """Instance Health Check

     Get health status of a specific instance.

    Args:
        instance_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
    """

    return sync_detailed(
        instance_id=instance_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    instance_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
]:
    """Instance Health Check

     Get health status of a specific instance.

    Args:
        instance_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet]
    """

    kwargs = _get_kwargs(
        instance_id=instance_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    instance_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    HTTPValidationError
    | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
    | None
):
    """Instance Health Check

     Get health status of a specific instance.

    Args:
        instance_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InstanceHealthCheckHealthInstancesInstanceIdGetResponseInstanceHealthCheckHealthInstancesInstanceIdGet
    """

    return (
        await asyncio_detailed(
            instance_id=instance_id,
            client=client,
        )
    ).parsed
