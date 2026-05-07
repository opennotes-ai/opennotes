"""Schema contracts for weather-report style axis confidence outputs."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

LabelT = TypeVar("LabelT")


TruthLabel = Literal[
    "sourced",
    "mostly_factual",
    "self_reported",
    "hearsay",
    "misleading",
]


RelevanceLabel = Literal["insightful", "on_topic", "chatty", "drifting", "off_topic"]


class WeatherAxisAlternative(BaseModel, Generic[LabelT]):
    label: LabelT
    logprob: float | None = None


class WeatherAxis(BaseModel, Generic[LabelT]):
    label: LabelT
    logprob: float | None = None
    alternatives: list[WeatherAxisAlternative[LabelT]] = Field(default_factory=list)


class WeatherAxisAlternativeTruth(WeatherAxisAlternative[TruthLabel]):
    """WeatherAxisAlternative[TruthLabel] with a stable schema name."""


class WeatherAxisAlternativeRelevance(WeatherAxisAlternative[RelevanceLabel]):
    """WeatherAxisAlternative[RelevanceLabel] with a stable schema name."""


class WeatherAxisAlternativeSentiment(WeatherAxisAlternative[str]):
    """WeatherAxisAlternative[str] with a stable schema name."""


class WeatherAxisTruth(WeatherAxis[TruthLabel]):
    """WeatherAxis[TruthLabel] with a stable schema name."""

    alternatives: list[WeatherAxisAlternativeTruth] = Field(
        default_factory=list,
    )


class WeatherAxisRelevance(WeatherAxis[RelevanceLabel]):
    """WeatherAxis[RelevanceLabel] with a stable schema name."""

    alternatives: list[WeatherAxisAlternativeRelevance] = Field(
        default_factory=list,
    )


class WeatherAxisSentiment(WeatherAxis[str]):
    """WeatherAxis[str] with a stable schema name."""

    alternatives: list[WeatherAxisAlternativeSentiment] = Field(
        default_factory=list,
    )


class WeatherReport(BaseModel):
    truth: WeatherAxisTruth
    relevance: WeatherAxisRelevance
    sentiment: WeatherAxisSentiment
