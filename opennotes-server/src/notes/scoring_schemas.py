from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.common.base_schemas import SQLAlchemySchema


class ScorerTier(str, Enum):
    MINIMAL = "minimal"
    LIMITED = "limited"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    FULL = "full"


class DataConfidence(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ScoreConfidence(str, Enum):
    NO_DATA = "no_data"
    PROVISIONAL = "provisional"
    STANDARD = "standard"


class TierInfo(BaseModel):
    level: int = Field(..., description="Numeric tier level (0-5)")
    name: str = Field(..., description="Human-readable tier name")
    scorer_components: list[str] = Field(
        ..., description="List of scorer components active in this tier"
    )


class TierThreshold(BaseModel):
    min: int = Field(..., description="Minimum note count for this tier")
    max: int | None = Field(
        ..., description="Maximum note count for this tier (null for unlimited)"
    )
    current: bool = Field(..., description="Whether this is the currently active tier")


class NextTierInfo(BaseModel):
    tier: str = Field(..., description="Name of the next tier")
    notes_needed: int = Field(..., description="Total notes needed to reach next tier")
    notes_to_upgrade: int = Field(
        ..., description="Additional notes needed (negative means already exceeded)"
    )


class PerformanceMetrics(BaseModel):
    avg_scoring_time_ms: float = Field(..., description="Average scoring time in milliseconds")
    last_scoring_time_ms: float | None = Field(
        None, description="Last scoring operation time in milliseconds"
    )
    scorer_success_rate: float = Field(
        ..., description="Success rate for scoring operations (0.0-1.0)"
    )
    total_scoring_operations: int = Field(
        0, description="Total number of scoring operations performed"
    )
    failed_scoring_operations: int = Field(0, description="Number of failed scoring operations")


class ScoringStatusResponse(SQLAlchemySchema):
    current_note_count: int = Field(..., description="Current total number of notes in the system")
    active_tier: TierInfo = Field(..., description="Currently active scoring tier information")
    data_confidence: DataConfidence = Field(
        ..., description="Confidence level in scoring results based on data volume"
    )
    tier_thresholds: dict[str, TierThreshold] = Field(
        ..., description="Threshold information for all tiers"
    )
    next_tier_upgrade: NextTierInfo | None = Field(
        None, description="Information about the next tier upgrade (null if at max tier)"
    )
    performance_metrics: PerformanceMetrics = Field(
        ..., description="Performance metrics for the scoring system"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Any warnings about data quality or scoring limitations"
    )
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Current scoring configuration overrides"
    )


class TierConfig(BaseModel):
    level: int
    name: str
    min_notes: int
    max_notes: int | None
    scorers: list[str]
    confidence: DataConfidence
    description: str


class NoteScoreResponse(SQLAlchemySchema):
    note_id: UUID = Field(..., description="Unique note identifier")
    score: float = Field(..., description="Normalized score value (0.0-1.0)")
    confidence: ScoreConfidence = Field(
        ...,
        description="Confidence level: no_data (0 ratings), provisional (<5 ratings), or standard (5+ ratings)",
    )
    algorithm: str = Field(
        ..., description="Scoring algorithm used (e.g., 'bayesian_average_tier0', 'MFCoreScorer')"
    )
    rating_count: int = Field(..., description="Number of ratings contributing to the score")
    tier: int = Field(..., description="Current scoring tier level (0-5)")
    tier_name: str = Field(..., description="Human-readable tier name (e.g., 'Minimal', 'Limited')")
    calculated_at: datetime | None = Field(
        None, description="Timestamp when score was calculated (null if not yet calculated)"
    )
    content: str | None = Field(
        None, description="Message content that the note was written about (from message archive)"
    )


class NoteData(BaseModel):
    noteId: int
    noteAuthorParticipantId: str
    createdAtMillis: int
    tweetId: int
    summary: str
    classification: str


class RatingData(BaseModel):
    raterParticipantId: str
    noteId: int
    createdAtMillis: int
    helpfulnessLevel: str


class EnrollmentData(BaseModel):
    participantId: str
    enrollmentState: str
    successfulRatingNeededToEarnIn: int
    timestampOfLastStateChange: int


class ScoringRequest(BaseModel):
    notes: list[NoteData] = Field(..., description="List of community notes to score")
    ratings: list[RatingData] = Field(..., description="List of ratings for the notes")
    enrollment: list[EnrollmentData] = Field(..., description="List of user enrollment data")
    status: list[dict[str, Any]] | None = Field(
        default=None, description="Optional note status history"
    )


class ScoringResponse(SQLAlchemySchema):
    scored_notes: list[dict[str, Any]]
    helpful_scores: list[dict[str, Any]]
    auxiliary_info: list[dict[str, Any]]
