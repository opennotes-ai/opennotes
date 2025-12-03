"""
Tests for UserEnrollmentBuilder.

TDD: Write failing tests first, then implement.
"""

import pandas as pd


class TestUserEnrollmentBuilder:
    """Tests for UserEnrollmentBuilder (AC #3)."""

    def test_can_import_user_enrollment_builder(self):
        """UserEnrollmentBuilder can be imported."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        assert UserEnrollmentBuilder is not None

    def test_builder_can_be_instantiated(self):
        """UserEnrollmentBuilder can be instantiated."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        assert builder is not None

    def test_build_returns_dataframe(self):
        """build() returns a pandas DataFrame."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build([])

        assert isinstance(result, pd.DataFrame)

    def test_build_with_empty_list_returns_empty_dataframe_with_columns(self):
        """build() with empty list returns DataFrame with required columns."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build([])

        assert len(result) == 0
        assert "participantId" in result.columns
        assert "modelingGroup" in result.columns


class TestUserEnrollmentBuilderWithParticipants:
    """Tests for UserEnrollmentBuilder with participant data (AC #3)."""

    def test_build_with_single_participant(self):
        """build() correctly transforms a single participant ID."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build(["discord_user_123"])

        assert len(result) == 1
        assert result.iloc[0]["participantId"] == "discord_user_123"

    def test_build_with_include_unassigned_true(self):
        """build() with include_unassigned=True assigns all users to stable initialization group 13."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build(["user_1", "user_2"], include_unassigned=True)

        assert len(result) == 2
        assert result.iloc[0]["modelingGroup"] == 13
        assert result.iloc[1]["modelingGroup"] == 13

    def test_build_defaults_to_include_unassigned_true(self):
        """build() defaults to include_unassigned=True."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build(["user_1"])

        assert result.iloc[0]["modelingGroup"] == 13

    def test_build_with_multiple_participants(self):
        """build() correctly transforms multiple participant IDs."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        participant_ids = ["user_1", "user_2", "user_3"]

        builder = UserEnrollmentBuilder()
        result = builder.build(participant_ids)

        assert len(result) == 3
        assert list(result["participantId"]) == participant_ids

    def test_build_preserves_participant_id_order(self):
        """build() preserves the order of participant IDs."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        participant_ids = ["zebra_user", "apple_user", "mango_user"]

        builder = UserEnrollmentBuilder()
        result = builder.build(participant_ids)

        assert list(result["participantId"]) == participant_ids


class TestUserEnrollmentBuilderModelingGroups:
    """Tests for UserEnrollmentBuilder modeling group assignment."""

    def test_all_participants_same_group_with_include_unassigned(self):
        """All participants get the stable initialization modeling group (13) when include_unassigned=True."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build(["user_1", "user_2", "user_3", "user_4", "user_5"])

        groups = result["modelingGroup"].unique()
        assert len(groups) == 1
        assert groups[0] == 13

    def test_modeling_group_is_numeric(self):
        """modelingGroup column is numeric."""
        from src.notes.scoring.user_enrollment_builder import UserEnrollmentBuilder

        builder = UserEnrollmentBuilder()
        result = builder.build(["user_1"])

        assert result["modelingGroup"].dtype in ["int64", "float64", "int32"]
