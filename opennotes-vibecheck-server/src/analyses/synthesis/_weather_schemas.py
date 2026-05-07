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


class WeatherReport(BaseModel):
    truth: WeatherAxis[TruthLabel]
    relevance: WeatherAxis[RelevanceLabel]
    sentiment: WeatherAxis[str]
