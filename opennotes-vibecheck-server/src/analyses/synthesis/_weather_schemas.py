"""Schema contracts for weather-report style axis confidence outputs."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

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


def _weather_schema_name(title: str) -> str | None:
    return {
        "WeatherAxisAlternative[Literal['insightful', 'on_topic', 'chatty', 'drifting', 'off_topic']]": "WeatherAxisAlternativeRelevance",
        "WeatherAxisAlternative[Literal['sourced', 'mostly_factual', 'self_reported', 'hearsay', 'misleading']]": "WeatherAxisAlternativeTruth",
        "WeatherAxisAlternative[str]": "WeatherAxisAlternativeSentiment",
        "WeatherAxis[Literal['insightful', 'on_topic', 'chatty', 'drifting', 'off_topic']]": "WeatherAxisRelevance",
        "WeatherAxis[Literal['sourced', 'mostly_factual', 'self_reported', 'hearsay', 'misleading']]": "WeatherAxisTruth",
        "WeatherAxis[str]": "WeatherAxisSentiment",
    }.get(title)


def _normalize_weather_schema_names(schema: dict[str, Any]) -> dict[str, Any]:
    ref_prefix: str | None = None
    if isinstance(schema.get("$defs"), dict):
        defs: dict[str, Any] = schema["$defs"]
        ref_prefix = "#/$defs/"
    else:
        components = schema.get("components")
        if isinstance(components, dict) and isinstance(
            components.get("schemas"),
            dict,
        ):
            defs = components["schemas"]
            ref_prefix = "#/components/schemas/"
        else:
            return schema

    if not isinstance(defs, dict):
        return schema

    rename_map: dict[str, str] = {}
    for old_name, definition in defs.items():
        target_name = _weather_schema_name(str(definition.get("title", "")))
        if target_name is not None:
            rename_map[old_name] = target_name

    for old_name, new_name in rename_map.items():
        if old_name == new_name:
            continue
        defs[new_name] = defs.pop(old_name)

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref" and isinstance(value, str):
                    if ref_prefix is None or not value.startswith(ref_prefix):
                        continue
                    prefix = ref_prefix
                    old_ref = value[len(prefix) :]
                    replacement = rename_map.get(old_ref)
                    if replacement is not None:
                        node[key] = prefix + replacement
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    return schema


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

    @classmethod
    def model_json_schema(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return _normalize_weather_schema_names(
            super().model_json_schema(*args, **kwargs),
        )
