from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delete_dataset_fusion_weight_api_v1_admin_fusion_weights_dataset_delete_response_delete_dataset_fusion_weight_api_v1_admin_fusion_weights_dataset_delete import (
    DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    dataset: str,
    *,
    x_api_key: None | str | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(x_api_key, Unset):
        headers["X-API-Key"] = x_api_key

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/v1/admin/fusion-weights/{dataset}".format(
            dataset=quote(str(dataset), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete.from_dict(
            response.json()
        )

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
) -> Response[
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    dataset: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
]:
    """Delete Dataset Fusion Weight

     Delete a dataset-specific fusion weight (revert to default).

    Args:
        dataset: Dataset name to remove override for

    Returns:
        dict: Confirmation message

    Args:
        dataset (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dataset=dataset,
        x_api_key=x_api_key,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    dataset: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> (
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
    | None
):
    """Delete Dataset Fusion Weight

     Delete a dataset-specific fusion weight (revert to default).

    Args:
        dataset: Dataset name to remove override for

    Returns:
        dict: Confirmation message

    Args:
        dataset (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete | HTTPValidationError
    """

    return sync_detailed(
        dataset=dataset,
        client=client,
        x_api_key=x_api_key,
    ).parsed


async def asyncio_detailed(
    dataset: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> Response[
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
]:
    """Delete Dataset Fusion Weight

     Delete a dataset-specific fusion weight (revert to default).

    Args:
        dataset: Dataset name to remove override for

    Returns:
        dict: Confirmation message

    Args:
        dataset (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        dataset=dataset,
        x_api_key=x_api_key,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    dataset: str,
    *,
    client: AuthenticatedClient,
    x_api_key: None | str | Unset = UNSET,
) -> (
    Any
    | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete
    | HTTPValidationError
    | None
):
    """Delete Dataset Fusion Weight

     Delete a dataset-specific fusion weight (revert to default).

    Args:
        dataset: Dataset name to remove override for

    Returns:
        dict: Confirmation message

    Args:
        dataset (str):
        x_api_key (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | DeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDeleteResponseDeleteDatasetFusionWeightApiV1AdminFusionWeightsDatasetDelete | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            dataset=dataset,
            client=client,
            x_api_key=x_api_key,
        )
    ).parsed
