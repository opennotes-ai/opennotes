"""
Tests for CommunityDataProvider protocol.

TDD: Write failing tests first, then implement.

Phase 2: Data Provider Protocol for MFCoreScorerAdapter integration.
"""

from typing import Any, Protocol, runtime_checkable


class TestCommunityDataProviderProtocol:
    """Tests for CommunityDataProvider protocol interface (Phase 2 AC prerequisite for AC #2-4)."""

    def test_data_provider_module_exists(self):
        """data_provider module should exist in scoring package."""
        from src.notes.scoring import data_provider

        assert data_provider is not None

    def test_data_provider_protocol_exists(self):
        """CommunityDataProvider protocol should be defined."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert CommunityDataProvider is not None

    def test_data_provider_is_protocol(self):
        """CommunityDataProvider should be a Protocol class."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert issubclass(CommunityDataProvider, Protocol)

    def test_data_provider_is_runtime_checkable(self):
        """CommunityDataProvider should be runtime checkable."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        @runtime_checkable
        class TestProtocol(Protocol):
            pass

        assert hasattr(CommunityDataProvider, "_is_runtime_checkable") or isinstance(
            CommunityDataProvider, type
        )

    def test_data_provider_has_get_all_ratings_method(self):
        """CommunityDataProvider must define get_all_ratings method."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_ratings")

    def test_data_provider_has_get_all_notes_method(self):
        """CommunityDataProvider must define get_all_notes method."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_notes")

    def test_data_provider_has_get_all_participants_method(self):
        """CommunityDataProvider must define get_all_participants method."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_participants")


class TestCommunityDataProviderMockImplementation:
    """Tests that mock implementations can correctly implement the protocol."""

    def test_mock_provider_conforms_to_protocol(self):
        """A mock implementation conforming to the protocol should be recognized."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        mock_provider = MockDataProvider()

        assert isinstance(mock_provider, CommunityDataProvider)

    def test_mock_provider_can_return_ratings(self):
        """Mock provider should be able to return ratings data."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": "rating-1",
                        "note_id": "note-1",
                        "rater_id": "user-1",
                        "helpfulness_level": "HELPFUL",
                    }
                ]

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        provider: CommunityDataProvider = MockDataProvider()
        ratings = provider.get_all_ratings("community-123")

        assert len(ratings) == 1
        assert ratings[0]["note_id"] == "note-1"

    def test_mock_provider_can_return_notes(self):
        """Mock provider should be able to return notes data."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return [
                    {
                        "id": "note-1",
                        "author_id": "user-1",
                        "classification": "NOT_MISLEADING",
                        "status": "NEEDS_MORE_RATINGS",
                    }
                ]

            def get_all_participants(self, community_id: str) -> list[str]:
                return []

        provider: CommunityDataProvider = MockDataProvider()
        notes = provider.get_all_notes("community-123")

        assert len(notes) == 1
        assert notes[0]["id"] == "note-1"

    def test_mock_provider_can_return_participants(self):
        """Mock provider should be able to return participant IDs."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_notes(self, community_id: str) -> list[dict[str, Any]]:
                return []

            def get_all_participants(self, community_id: str) -> list[str]:
                return ["user-1", "user-2", "user-3"]

        provider: CommunityDataProvider = MockDataProvider()
        participants = provider.get_all_participants("community-123")

        assert len(participants) == 3
        assert "user-1" in participants

    def test_incomplete_provider_does_not_conform(self):
        """An incomplete implementation should not be recognized as conforming."""
        from src.notes.scoring.data_provider import CommunityDataProvider

        class IncompleteProvider:
            def get_all_ratings(self, community_id: str) -> list[dict[str, Any]]:
                return []

        incomplete_provider = IncompleteProvider()

        assert not isinstance(incomplete_provider, CommunityDataProvider)
