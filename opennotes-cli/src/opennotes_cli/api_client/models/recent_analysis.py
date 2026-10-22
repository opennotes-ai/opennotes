from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.safety_row_preview import SafetyRowPreview


T = TypeVar("T", bound="RecentAnalysis")


@_attrs_define
class RecentAnalysis:
    """
    Attributes:
        job_id (UUID): batch_jobs.id for the analysis job.
        source_url (str):
        screenshot_url (str): Signed screenshot URL for the gallery card.
        preview_description (str): Short non-null gallery blurb.
        completed_at (datetime.datetime):
        page_title (None | str | Unset):
        og_thumbnail_url (None | str | Unset): X (Twitter) OG thumbnail URL stored during scan; None for non-X URLs.
        headline_preview (None | str | Unset): Truncated headline summary text from sidebar_payload; None when absent.
        weather_preview (None | str | Unset): Compact weather-report label string (truth · relevance · sentiment); None
            when absent.
        safety_row (None | SafetyRowPreview | Unset): Minimal safety summary for gallery row; None when no
            recommendation stored.
    """

    job_id: UUID
    source_url: str
    screenshot_url: str
    preview_description: str
    completed_at: datetime.datetime
    page_title: None | str | Unset = UNSET
    og_thumbnail_url: None | str | Unset = UNSET
    headline_preview: None | str | Unset = UNSET
    weather_preview: None | str | Unset = UNSET
    safety_row: None | SafetyRowPreview | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.safety_row_preview import SafetyRowPreview

        job_id = str(self.job_id)

        source_url = self.source_url

        screenshot_url = self.screenshot_url

        preview_description = self.preview_description

        completed_at = self.completed_at.isoformat()

        page_title: None | str | Unset
        if isinstance(self.page_title, Unset):
            page_title = UNSET
        else:
            page_title = self.page_title

        og_thumbnail_url: None | str | Unset
        if isinstance(self.og_thumbnail_url, Unset):
            og_thumbnail_url = UNSET
        else:
            og_thumbnail_url = self.og_thumbnail_url

        headline_preview: None | str | Unset
        if isinstance(self.headline_preview, Unset):
            headline_preview = UNSET
        else:
            headline_preview = self.headline_preview

        weather_preview: None | str | Unset
        if isinstance(self.weather_preview, Unset):
            weather_preview = UNSET
        else:
            weather_preview = self.weather_preview

        safety_row: dict[str, Any] | None | Unset
        if isinstance(self.safety_row, Unset):
            safety_row = UNSET
        elif isinstance(self.safety_row, SafetyRowPreview):
            safety_row = self.safety_row.to_dict()
        else:
            safety_row = self.safety_row

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
                "source_url": source_url,
                "screenshot_url": screenshot_url,
                "preview_description": preview_description,
                "completed_at": completed_at,
            }
        )
        if page_title is not UNSET:
            field_dict["page_title"] = page_title
        if og_thumbnail_url is not UNSET:
            field_dict["og_thumbnail_url"] = og_thumbnail_url
        if headline_preview is not UNSET:
            field_dict["headline_preview"] = headline_preview
        if weather_preview is not UNSET:
            field_dict["weather_preview"] = weather_preview
        if safety_row is not UNSET:
            field_dict["safety_row"] = safety_row

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.safety_row_preview import SafetyRowPreview

        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        source_url = d.pop("source_url")

        screenshot_url = d.pop("screenshot_url")

        preview_description = d.pop("preview_description")

        completed_at = isoparse(d.pop("completed_at"))

        def _parse_page_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        page_title = _parse_page_title(d.pop("page_title", UNSET))

        def _parse_og_thumbnail_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        og_thumbnail_url = _parse_og_thumbnail_url(d.pop("og_thumbnail_url", UNSET))

        def _parse_headline_preview(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        headline_preview = _parse_headline_preview(d.pop("headline_preview", UNSET))

        def _parse_weather_preview(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        weather_preview = _parse_weather_preview(d.pop("weather_preview", UNSET))

        def _parse_safety_row(data: object) -> None | SafetyRowPreview | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                safety_row_type_0 = SafetyRowPreview.from_dict(data)

                return safety_row_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SafetyRowPreview | Unset, data)

        safety_row = _parse_safety_row(d.pop("safety_row", UNSET))

        recent_analysis = cls(
            job_id=job_id,
            source_url=source_url,
            screenshot_url=screenshot_url,
            preview_description=preview_description,
            completed_at=completed_at,
            page_title=page_title,
            og_thumbnail_url=og_thumbnail_url,
            headline_preview=headline_preview,
            weather_preview=weather_preview,
            safety_row=safety_row,
        )

        recent_analysis.additional_properties = d
        return recent_analysis

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
