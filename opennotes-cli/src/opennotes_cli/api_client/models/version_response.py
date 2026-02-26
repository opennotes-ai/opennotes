from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="VersionResponse")


@_attrs_define
class VersionResponse:
    """
    Attributes:
        git_sha (None | str | Unset): Git commit SHA
        build_date (None | str | Unset): Build timestamp
        revision (None | str | Unset): Cloud Run revision name
    """

    git_sha: None | str | Unset = UNSET
    build_date: None | str | Unset = UNSET
    revision: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        git_sha: None | str | Unset
        if isinstance(self.git_sha, Unset):
            git_sha = UNSET
        else:
            git_sha = self.git_sha

        build_date: None | str | Unset
        if isinstance(self.build_date, Unset):
            build_date = UNSET
        else:
            build_date = self.build_date

        revision: None | str | Unset
        if isinstance(self.revision, Unset):
            revision = UNSET
        else:
            revision = self.revision

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if git_sha is not UNSET:
            field_dict["git_sha"] = git_sha
        if build_date is not UNSET:
            field_dict["build_date"] = build_date
        if revision is not UNSET:
            field_dict["revision"] = revision

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_git_sha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        git_sha = _parse_git_sha(d.pop("git_sha", UNSET))

        def _parse_build_date(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        build_date = _parse_build_date(d.pop("build_date", UNSET))

        def _parse_revision(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        revision = _parse_revision(d.pop("revision", UNSET))

        version_response = cls(
            git_sha=git_sha,
            build_date=build_date,
            revision=revision,
        )

        version_response.additional_properties = d
        return version_response

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
