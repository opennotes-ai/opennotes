from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.facts_claims_section import FactsClaimsSection
    from ..models.headline_summary import HeadlineSummary
    from ..models.image_moderation_section import ImageModerationSection
    from ..models.opinions_section import OpinionsSection
    from ..models.overall_decision import OverallDecision
    from ..models.safety_section import SafetySection
    from ..models.tone_dynamics_section import ToneDynamicsSection
    from ..models.utterance_anchor import UtteranceAnchor
    from ..models.video_moderation_section import VideoModerationSection
    from ..models.weather_report import WeatherReport
    from ..models.web_risk_section import WebRiskSection


T = TypeVar("T", bound="SidebarPayload")


@_attrs_define
class SidebarPayload:
    """
    Attributes:
        scraped_at (datetime.datetime):
        safety (SafetySection):
        tone_dynamics (ToneDynamicsSection):
        facts_claims (FactsClaimsSection):
        opinions_sentiments (OpinionsSection):
        cached (bool | Unset):  Default: False.
        cached_at (datetime.datetime | None | Unset):
        web_risk (WebRiskSection | Unset):
        image_moderation (ImageModerationSection | Unset):
        video_moderation (VideoModerationSection | Unset):
        headline (HeadlineSummary | None | Unset):
        weather_report (None | Unset | WeatherReport):
        overall_recommendation (None | OverallDecision | Unset):
        utterances (list[UtteranceAnchor] | Unset):
    """

    scraped_at: datetime.datetime
    safety: SafetySection
    tone_dynamics: ToneDynamicsSection
    facts_claims: FactsClaimsSection
    opinions_sentiments: OpinionsSection
    cached: bool | Unset = False
    cached_at: datetime.datetime | None | Unset = UNSET
    web_risk: WebRiskSection | Unset = UNSET
    image_moderation: ImageModerationSection | Unset = UNSET
    video_moderation: VideoModerationSection | Unset = UNSET
    headline: HeadlineSummary | None | Unset = UNSET
    weather_report: None | Unset | WeatherReport = UNSET
    overall_recommendation: None | OverallDecision | Unset = UNSET
    utterances: list[UtteranceAnchor] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.headline_summary import HeadlineSummary
        from ..models.overall_decision import OverallDecision
        from ..models.weather_report import WeatherReport

        scraped_at = self.scraped_at.isoformat()

        safety = self.safety.to_dict()

        tone_dynamics = self.tone_dynamics.to_dict()

        facts_claims = self.facts_claims.to_dict()

        opinions_sentiments = self.opinions_sentiments.to_dict()

        cached = self.cached

        cached_at: None | str | Unset
        if isinstance(self.cached_at, Unset):
            cached_at = UNSET
        elif isinstance(self.cached_at, datetime.datetime):
            cached_at = self.cached_at.isoformat()
        else:
            cached_at = self.cached_at

        web_risk: dict[str, Any] | Unset = UNSET
        if not isinstance(self.web_risk, Unset):
            web_risk = self.web_risk.to_dict()

        image_moderation: dict[str, Any] | Unset = UNSET
        if not isinstance(self.image_moderation, Unset):
            image_moderation = self.image_moderation.to_dict()

        video_moderation: dict[str, Any] | Unset = UNSET
        if not isinstance(self.video_moderation, Unset):
            video_moderation = self.video_moderation.to_dict()

        headline: dict[str, Any] | None | Unset
        if isinstance(self.headline, Unset):
            headline = UNSET
        elif isinstance(self.headline, HeadlineSummary):
            headline = self.headline.to_dict()
        else:
            headline = self.headline

        weather_report: dict[str, Any] | None | Unset
        if isinstance(self.weather_report, Unset):
            weather_report = UNSET
        elif isinstance(self.weather_report, WeatherReport):
            weather_report = self.weather_report.to_dict()
        else:
            weather_report = self.weather_report

        overall_recommendation: dict[str, Any] | None | Unset
        if isinstance(self.overall_recommendation, Unset):
            overall_recommendation = UNSET
        elif isinstance(self.overall_recommendation, OverallDecision):
            overall_recommendation = self.overall_recommendation.to_dict()
        else:
            overall_recommendation = self.overall_recommendation

        utterances: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.utterances, Unset):
            utterances = []
            for utterances_item_data in self.utterances:
                utterances_item = utterances_item_data.to_dict()
                utterances.append(utterances_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "scraped_at": scraped_at,
                "safety": safety,
                "tone_dynamics": tone_dynamics,
                "facts_claims": facts_claims,
                "opinions_sentiments": opinions_sentiments,
            }
        )
        if cached is not UNSET:
            field_dict["cached"] = cached
        if cached_at is not UNSET:
            field_dict["cached_at"] = cached_at
        if web_risk is not UNSET:
            field_dict["web_risk"] = web_risk
        if image_moderation is not UNSET:
            field_dict["image_moderation"] = image_moderation
        if video_moderation is not UNSET:
            field_dict["video_moderation"] = video_moderation
        if headline is not UNSET:
            field_dict["headline"] = headline
        if weather_report is not UNSET:
            field_dict["weather_report"] = weather_report
        if overall_recommendation is not UNSET:
            field_dict["overall_recommendation"] = overall_recommendation
        if utterances is not UNSET:
            field_dict["utterances"] = utterances

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facts_claims_section import FactsClaimsSection
        from ..models.headline_summary import HeadlineSummary
        from ..models.image_moderation_section import ImageModerationSection
        from ..models.opinions_section import OpinionsSection
        from ..models.overall_decision import OverallDecision
        from ..models.safety_section import SafetySection
        from ..models.tone_dynamics_section import ToneDynamicsSection
        from ..models.utterance_anchor import UtteranceAnchor
        from ..models.video_moderation_section import VideoModerationSection
        from ..models.weather_report import WeatherReport
        from ..models.web_risk_section import WebRiskSection

        d = dict(src_dict)
        scraped_at = isoparse(d.pop("scraped_at"))

        safety = SafetySection.from_dict(d.pop("safety"))

        tone_dynamics = ToneDynamicsSection.from_dict(d.pop("tone_dynamics"))

        facts_claims = FactsClaimsSection.from_dict(d.pop("facts_claims"))

        opinions_sentiments = OpinionsSection.from_dict(d.pop("opinions_sentiments"))

        cached = d.pop("cached", UNSET)

        def _parse_cached_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                cached_at_type_0 = isoparse(data)

                return cached_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        cached_at = _parse_cached_at(d.pop("cached_at", UNSET))

        _web_risk = d.pop("web_risk", UNSET)
        web_risk: WebRiskSection | Unset
        if isinstance(_web_risk, Unset):
            web_risk = UNSET
        else:
            web_risk = WebRiskSection.from_dict(_web_risk)

        _image_moderation = d.pop("image_moderation", UNSET)
        image_moderation: ImageModerationSection | Unset
        if isinstance(_image_moderation, Unset):
            image_moderation = UNSET
        else:
            image_moderation = ImageModerationSection.from_dict(_image_moderation)

        _video_moderation = d.pop("video_moderation", UNSET)
        video_moderation: VideoModerationSection | Unset
        if isinstance(_video_moderation, Unset):
            video_moderation = UNSET
        else:
            video_moderation = VideoModerationSection.from_dict(_video_moderation)

        def _parse_headline(data: object) -> HeadlineSummary | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                headline_type_0 = HeadlineSummary.from_dict(data)

                return headline_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HeadlineSummary | None | Unset, data)

        headline = _parse_headline(d.pop("headline", UNSET))

        def _parse_weather_report(data: object) -> None | Unset | WeatherReport:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                weather_report_type_0 = WeatherReport.from_dict(data)

                return weather_report_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | WeatherReport, data)

        weather_report = _parse_weather_report(d.pop("weather_report", UNSET))

        def _parse_overall_recommendation(
            data: object,
        ) -> None | OverallDecision | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                overall_recommendation_type_0 = OverallDecision.from_dict(data)

                return overall_recommendation_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | OverallDecision | Unset, data)

        overall_recommendation = _parse_overall_recommendation(
            d.pop("overall_recommendation", UNSET)
        )

        _utterances = d.pop("utterances", UNSET)
        utterances: list[UtteranceAnchor] | Unset = UNSET
        if _utterances is not UNSET:
            utterances = []
            for utterances_item_data in _utterances:
                utterances_item = UtteranceAnchor.from_dict(utterances_item_data)

                utterances.append(utterances_item)

        sidebar_payload = cls(
            scraped_at=scraped_at,
            safety=safety,
            tone_dynamics=tone_dynamics,
            facts_claims=facts_claims,
            opinions_sentiments=opinions_sentiments,
            cached=cached,
            cached_at=cached_at,
            web_risk=web_risk,
            image_moderation=image_moderation,
            video_moderation=video_moderation,
            headline=headline,
            weather_report=weather_report,
            overall_recommendation=overall_recommendation,
            utterances=utterances,
        )

        sidebar_payload.additional_properties = d
        return sidebar_payload

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
