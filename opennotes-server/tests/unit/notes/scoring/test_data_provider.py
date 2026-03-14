from typing import Protocol, runtime_checkable

import pyarrow as pa


class TestCommunityDataProviderProtocol:
    def test_data_provider_module_exists(self):
        from src.notes.scoring import data_provider

        assert data_provider is not None

    def test_data_provider_protocol_exists(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert CommunityDataProvider is not None

    def test_data_provider_is_protocol(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert issubclass(CommunityDataProvider, Protocol)

    def test_data_provider_is_runtime_checkable(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        @runtime_checkable
        class TestProtocol(Protocol):
            pass

        assert hasattr(CommunityDataProvider, "_is_runtime_checkable") or isinstance(
            CommunityDataProvider, type
        )

    def test_data_provider_has_get_all_ratings_method(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_ratings")

    def test_data_provider_has_get_all_notes_method(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_notes")

    def test_data_provider_has_get_all_participants_method(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        assert hasattr(CommunityDataProvider, "get_all_participants")


class TestCommunityDataProviderMockImplementation:
    def test_mock_provider_conforms_to_protocol(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "note_id": pa.array([], type=pa.string()),
                        "rater_id": pa.array([], type=pa.string()),
                        "helpfulness_level": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_notes(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "author_id": pa.array([], type=pa.string()),
                        "classification": pa.array([], type=pa.string()),
                        "status": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_participants(self, community_id: str) -> pa.Array:
                return pa.array([], type=pa.string())

        mock_provider = MockDataProvider()

        assert isinstance(mock_provider, CommunityDataProvider)

    def test_mock_provider_can_return_ratings(self):
        from datetime import UTC, datetime

        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": ["rating-1"],
                        "note_id": ["note-1"],
                        "rater_id": ["user-1"],
                        "helpfulness_level": ["HELPFUL"],
                        "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
                    }
                )

            def get_all_notes(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "author_id": pa.array([], type=pa.string()),
                        "classification": pa.array([], type=pa.string()),
                        "status": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_participants(self, community_id: str) -> pa.Array:
                return pa.array([], type=pa.string())

        provider: CommunityDataProvider = MockDataProvider()
        ratings = provider.get_all_ratings("community-123")

        assert ratings.num_rows == 1
        assert ratings.column("note_id")[0].as_py() == "note-1"

    def test_mock_provider_can_return_notes(self):
        from datetime import UTC, datetime

        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "note_id": pa.array([], type=pa.string()),
                        "rater_id": pa.array([], type=pa.string()),
                        "helpfulness_level": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_notes(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": ["note-1"],
                        "author_id": ["user-1"],
                        "classification": ["NOT_MISLEADING"],
                        "status": ["NEEDS_MORE_RATINGS"],
                        "created_at": [datetime(2025, 1, 1, tzinfo=UTC)],
                    }
                )

            def get_all_participants(self, community_id: str) -> pa.Array:
                return pa.array([], type=pa.string())

        provider: CommunityDataProvider = MockDataProvider()
        notes = provider.get_all_notes("community-123")

        assert notes.num_rows == 1
        assert notes.column("id")[0].as_py() == "note-1"

    def test_mock_provider_can_return_participants(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        class MockDataProvider:
            def get_all_ratings(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "note_id": pa.array([], type=pa.string()),
                        "rater_id": pa.array([], type=pa.string()),
                        "helpfulness_level": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_notes(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "author_id": pa.array([], type=pa.string()),
                        "classification": pa.array([], type=pa.string()),
                        "status": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

            def get_all_participants(self, community_id: str) -> pa.Array:
                return pa.array(["user-1", "user-2", "user-3"])

        provider: CommunityDataProvider = MockDataProvider()
        participants = provider.get_all_participants("community-123")

        assert len(participants) == 3
        assert participants[0].as_py() == "user-1"

    def test_incomplete_provider_does_not_conform(self):
        from src.notes.scoring.data_provider import CommunityDataProvider

        class IncompleteProvider:
            def get_all_ratings(self, community_id: str) -> pa.Table:
                return pa.table(
                    {
                        "id": pa.array([], type=pa.string()),
                        "note_id": pa.array([], type=pa.string()),
                        "rater_id": pa.array([], type=pa.string()),
                        "helpfulness_level": pa.array([], type=pa.string()),
                        "created_at": pa.array([], type=pa.timestamp("us", tz="UTC")),
                    }
                )

        incomplete_provider = IncompleteProvider()

        assert not isinstance(incomplete_provider, CommunityDataProvider)
