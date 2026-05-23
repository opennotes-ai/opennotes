from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from dateutil.parser import isoparse

from ..types import UNSET, Unset

T = TypeVar("T", bound="FactCheckMatch")


@_attrs_define
class FactCheckMatch:
    """
    Attributes:
        claim_text (str):
        publisher (str):
        review_title (str):
        review_url (str):
        textual_rating (str):
        review_date (datetime.date | None | Unset):
    """

    claim_text: str
    publisher: str
    review_title: str
    review_url: str
    textual_rating: str
    review_date: datetime.date | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        claim_text = self.claim_text

        publisher = self.publisher

        review_title = self.review_title

        review_url = self.review_url

        textual_rating = self.textual_rating

        review_date: None | str | Unset
        if isinstance(self.review_date, Unset):
            review_date = UNSET
        elif isinstance(self.review_date, datetime.date):
            review_date = self.review_date.isoformat()
        else:
            review_date = self.review_date

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "claim_text": claim_text,
                "publisher": publisher,
                "review_title": review_title,
                "review_url": review_url,
                "textual_rating": textual_rating,
            }
        )
        if review_date is not UNSET:
            field_dict["review_date"] = review_date

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        claim_text = d.pop("claim_text")

        publisher = d.pop("publisher")

        review_title = d.pop("review_title")

        review_url = d.pop("review_url")

        textual_rating = d.pop("textual_rating")

        def _parse_review_date(data: object) -> datetime.date | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                review_date_type_0 = isoparse(data).date()

                return review_date_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.date | None | Unset, data)

        review_date = _parse_review_date(d.pop("review_date", UNSET))

        fact_check_match = cls(
            claim_text=claim_text,
            publisher=publisher,
            review_title=review_title,
            review_url=review_url,
            textual_rating=textual_rating,
            review_date=review_date,
        )

        fact_check_match.additional_properties = d
        return fact_check_match

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
