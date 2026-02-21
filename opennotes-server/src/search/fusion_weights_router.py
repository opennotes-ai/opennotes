"""
Admin endpoints for managing hybrid search fusion weights.

This module provides endpoints for managing the Convex Combination (CC)
fusion weight (alpha) used in hybrid search scoring:

    final_score = alpha * semantic_similarity + (1-alpha) * keyword_norm

The weight can be configured globally or per-dataset for fine-tuned
relevance optimization.

Security:
- All endpoints require service account authentication
- Changes are logged for audit purposes
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field

from src.auth.dependencies import get_current_user_or_api_key
from src.auth.permissions import is_service_account
from src.cache.redis_client import redis_client
from src.common.base_schemas import SQLAlchemySchema, StrictInputSchema
from src.common.responses import AUTHENTICATED_RESPONSES
from src.search.fusion_config import (
    FALLBACK_ALPHA,
    FusionConfig,
    get_fusion_alpha,
    set_fusion_alpha,
)
from src.users.models import User

router = APIRouter(
    prefix="/api/v1/admin/fusion-weights",
    tags=["admin", "search"],
    responses=AUTHENTICATED_RESPONSES,
)
logger = logging.getLogger(__name__)


class FusionWeightUpdate(StrictInputSchema):
    """Request model for updating fusion weight."""

    alpha: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fusion weight alpha ∈ [0, 1]. alpha=1.0 is pure semantic, alpha=0.0 is pure keyword.",
    )
    dataset: str | None = Field(
        default=None,
        description="Optional dataset name for dataset-specific override. None for global default.",
    )


class FusionWeightResponse(SQLAlchemySchema):
    """Response model for fusion weight."""

    alpha: float = Field(..., description="Current fusion weight alpha ∈ [0, 1]")
    dataset: str | None = Field(None, description="Dataset name or None for global default")
    source: str = Field(..., description="Source of the value: 'redis' or 'fallback'")


class AllFusionWeightsResponse(SQLAlchemySchema):
    """Response model for all fusion weights."""

    default: float = Field(..., description="Global default fusion weight")
    datasets: dict[str, float] = Field(
        default_factory=dict,
        description="Dataset-specific fusion weights",
    )


async def verify_service_account(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> User:
    """
    Verify that the current user is a service account.

    Only service accounts are allowed to modify fusion weights.
    """
    if not is_service_account(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can perform this action",
        )
    return current_user


@router.get("", response_model=AllFusionWeightsResponse)
async def get_all_fusion_weights(
    _service_account: Annotated[User, Depends(verify_service_account)],
) -> AllFusionWeightsResponse:
    """
    Get all configured fusion weights.

    Returns the global default weight and any dataset-specific overrides.

    Returns:
        AllFusionWeightsResponse: All configured fusion weights
    """
    config = FusionConfig(redis_client)
    alphas = await config.get_all_alphas()

    default = alphas.pop("default", FALLBACK_ALPHA)
    return AllFusionWeightsResponse(default=default, datasets=alphas)


@router.get("/default", response_model=FusionWeightResponse)
async def get_default_fusion_weight(
    _service_account: Annotated[User, Depends(verify_service_account)],
) -> FusionWeightResponse:
    """
    Get the global default fusion weight.

    Returns:
        FusionWeightResponse: Current default fusion weight
    """
    alpha = await get_fusion_alpha(redis_client)
    return FusionWeightResponse(
        alpha=alpha,
        dataset=None,
        source="redis" if alpha != FALLBACK_ALPHA else "fallback",
    )


@router.get("/{dataset}", response_model=FusionWeightResponse)
async def get_dataset_fusion_weight(
    dataset: str,
    _service_account: Annotated[User, Depends(verify_service_account)],
) -> FusionWeightResponse:
    """
    Get the fusion weight for a specific dataset.

    Args:
        dataset: Dataset name (e.g., 'snopes', 'politifact')

    Returns:
        FusionWeightResponse: Fusion weight for the dataset
    """
    alpha = await get_fusion_alpha(redis_client, dataset=dataset)
    return FusionWeightResponse(
        alpha=alpha,
        dataset=dataset,
        source="redis" if alpha != FALLBACK_ALPHA else "fallback",
    )


@router.put("", response_model=FusionWeightResponse)
async def update_fusion_weight(
    request: FusionWeightUpdate,
    service_account: Annotated[User, Depends(verify_service_account)],
) -> FusionWeightResponse:
    """
    Update a fusion weight (global or dataset-specific).

    Args:
        request: FusionWeightUpdate with alpha and optional dataset

    Returns:
        FusionWeightResponse: Updated fusion weight

    Raises:
        HTTPException 400: If alpha is out of range
        HTTPException 500: If Redis update fails
    """
    try:
        success = await set_fusion_alpha(
            redis_client,
            alpha=request.alpha,
            dataset=request.dataset,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update fusion weight in Redis",
        )

    logger.info(
        "Fusion weight updated",
        extra={
            "alpha": request.alpha,
            "dataset": request.dataset or "default",
            "updated_by": service_account.username,
        },
    )

    return FusionWeightResponse(
        alpha=request.alpha,
        dataset=request.dataset,
        source="redis",
    )


@router.delete("/{dataset}", response_model=dict[str, str])
async def delete_dataset_fusion_weight(
    dataset: str,
    service_account: Annotated[User, Depends(verify_service_account)],
) -> dict[str, str]:
    """
    Delete a dataset-specific fusion weight (revert to default).

    Args:
        dataset: Dataset name to remove override for

    Returns:
        dict: Confirmation message
    """
    key = f"search:fusion:alpha:{dataset}"
    try:
        deleted = await redis_client.delete(key)
        if deleted:
            logger.info(
                "Dataset fusion weight deleted",
                extra={
                    "dataset": dataset,
                    "deleted_by": service_account.username,
                },
            )
            return {"message": f"Fusion weight for dataset '{dataset}' deleted, will use default"}
        return {"message": f"No fusion weight found for dataset '{dataset}'"}
    except Exception as e:
        logger.error(f"Failed to delete fusion weight: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete fusion weight",
        )
