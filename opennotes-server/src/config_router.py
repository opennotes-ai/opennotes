from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field

from src.auth.dependencies import get_current_user_or_api_key
from src.common.base_schemas import SQLAlchemySchema
from src.common.responses import AUTHENTICATED_RESPONSES
from src.config import settings
from src.monitoring import get_logger
from src.users.models import User

logger = get_logger(__name__)

router = APIRouter(tags=["config"], responses=AUTHENTICATED_RESPONSES)


class RatingThresholdsResponse(SQLAlchemySchema):
    min_ratings_needed: int = Field(
        ...,
        description="Minimum number of ratings before a note can receive CRH/CRNH status",
    )
    min_raters_per_note: int = Field(
        ...,
        description="Minimum number of unique raters required per note",
    )


@router.get("/config/rating-thresholds", response_model=RatingThresholdsResponse)
async def get_rating_thresholds(
    current_user: Annotated[User, Depends(get_current_user_or_api_key)],
) -> RatingThresholdsResponse:
    """
    Get rating threshold configuration values.

    These values define the minimum number of ratings and unique raters required
    before a note can receive CURRENTLY_RATED_HELPFUL or CURRENTLY_RATED_NOT_HELPFUL status.

    The thresholds should match the Community Notes scoring algorithm defaults.
    """
    logger.debug(f"User {current_user.id} requested rating thresholds")

    return RatingThresholdsResponse(
        min_ratings_needed=settings.MIN_RATINGS_NEEDED,
        min_raters_per_note=settings.MIN_RATERS_PER_NOTE,
    )
