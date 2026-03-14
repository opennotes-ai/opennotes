from typing import Any

import pytest


@pytest.mark.unit
class TestPreloadedDataProvider:
    def test_can_be_instantiated(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        provider = PreloadedDataProvider(ratings=[], notes=[], participants=[])
        assert provider is not None

    def test_get_all_ratings_returns_provided_data(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        ratings: list[dict[str, Any]] = [
            {"id": "r1", "note_id": "n1", "rater_id": "u1", "helpfulness_level": "HELPFUL"},
        ]
        provider = PreloadedDataProvider(ratings=ratings, notes=[], participants=[])

        result = provider.get_all_ratings("any-community")
        assert result == ratings

    def test_get_all_notes_returns_provided_data(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        notes: list[dict[str, Any]] = [
            {"id": "n1", "author_id": "u1", "classification": "MISINFORMED", "status": "CRH"},
        ]
        provider = PreloadedDataProvider(ratings=[], notes=notes, participants=[])

        result = provider.get_all_notes("any-community")
        assert result == notes

    def test_get_all_participants_returns_provided_data(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        participants = ["user-1", "user-2", "user-3"]
        provider = PreloadedDataProvider(ratings=[], notes=[], participants=participants)

        result = provider.get_all_participants("any-community")
        assert result == participants

    def test_community_id_parameter_is_ignored(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        ratings: list[dict[str, Any]] = [{"id": "r1"}]
        notes: list[dict[str, Any]] = [{"id": "n1"}]
        participants = ["u1"]
        provider = PreloadedDataProvider(ratings=ratings, notes=notes, participants=participants)

        assert provider.get_all_ratings("community-A") == ratings
        assert provider.get_all_ratings("community-B") == ratings
        assert provider.get_all_notes("community-A") == notes
        assert provider.get_all_participants("community-A") == participants

    def test_satisfies_community_data_provider_protocol(self):
        from src.notes.scoring.data_provider import CommunityDataProvider
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        provider = PreloadedDataProvider(ratings=[], notes=[], participants=[])
        assert isinstance(provider, CommunityDataProvider)

    def test_empty_data(self):
        from src.notes.scoring.preloaded_data_provider import PreloadedDataProvider

        provider = PreloadedDataProvider(ratings=[], notes=[], participants=[])

        assert provider.get_all_ratings("c") == []
        assert provider.get_all_notes("c") == []
        assert provider.get_all_participants("c") == []
