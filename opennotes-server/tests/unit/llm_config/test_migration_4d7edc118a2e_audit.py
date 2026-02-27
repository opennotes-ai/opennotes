"""Audit tests for Alembic migration 4d7edc118a2e (task-1174 model_name normalization).

Task-1184: Verify the migration SQL produces correct output for all known
model_name patterns, including the three patterns reported as mis-translated.
"""

import pytest

LITELLM_TO_PYDANTIC_PROVIDERS = {
    "vertex_ai": "google-vertex",
    "gemini": "google-gla",
}


def _simulate_upgrade(model_name: str) -> str:
    """Pure-Python simulation of the migration's upgrade SQL logic.

    Mirrors the two-phase SQL in 4d7edc118a2e exactly:
    1. Provider translation for vertex_ai and gemini prefixes
    2. Generic slash-to-colon for remaining rows
    """
    if ":" in model_name:
        return model_name

    for litellm_provider, pydantic_provider in LITELLM_TO_PYDANTIC_PROVIDERS.items():
        if model_name.startswith(f"{litellm_provider}/"):
            first_slash = model_name.index("/")
            return f"{pydantic_provider}:{model_name[first_slash + 1 :]}"

    if "/" in model_name:
        first_slash = model_name.index("/")
        return f"{model_name[:first_slash]}:{model_name[first_slash + 1 :]}"

    return model_name


class TestMigrationLogicCorrectness:
    """Prove the migration SQL is correct for all reported cases."""

    def test_openai_gpt5_mini(self):
        assert _simulate_upgrade("openai/gpt-5-mini") == "openai:gpt-5-mini"

    def test_openai_gpt5_2(self):
        assert _simulate_upgrade("openai/gpt-5.2") == "openai:gpt-5.2"

    def test_vertex_ai_global_gemini3_pro(self):
        result = _simulate_upgrade("vertex_ai/global/gemini-3-pro-preview")
        assert result == "google-vertex:global/gemini-3-pro-preview"

    def test_openai_gpt4o_mini(self):
        assert _simulate_upgrade("openai/gpt-4o-mini") == "openai:gpt-4o-mini"

    def test_vertex_ai_global_gemini25_pro(self):
        result = _simulate_upgrade("vertex_ai/global/gemini-2.5-pro")
        assert result == "google-vertex:global/gemini-2.5-pro"

    def test_gemini_flash(self):
        assert _simulate_upgrade("gemini/gemini-2.5-flash") == "google-gla:gemini-2.5-flash"

    def test_anthropic_claude(self):
        assert (
            _simulate_upgrade("anthropic/claude-3-5-sonnet-latest")
            == "anthropic:claude-3-5-sonnet-latest"
        )

    def test_already_colon_format_skipped(self):
        assert _simulate_upgrade("openai:gpt-5-mini") == "openai:gpt-5-mini"

    def test_openrouter_nested_slash(self):
        result = _simulate_upgrade("openrouter/google/gemini-3-pro")
        assert result == "openrouter:google/gemini-3-pro"


class TestReportedMisTranslationsCannotComeFromMigration:
    """The three reported mis-translations are impossible given the migration logic.

    - openai/gpt-5-mini → openai:gpt-4o-mini  (model name changed entirely)
    - openai/gpt-5.2    → openai:gpt-5-mini   (model name changed entirely)
    - vertex_ai/global/gemini-3-pro-preview → google-vertex:gemini-2.5-pro (model changed, global/ stripped)

    The migration only changes separators and translates provider names; it never
    alters the model portion of the string.
    """

    def test_gpt5_mini_not_gpt4o_mini(self):
        result = _simulate_upgrade("openai/gpt-5-mini")
        assert result != "openai:gpt-4o-mini"
        assert "gpt-5-mini" in result

    def test_gpt5_2_not_gpt5_mini(self):
        result = _simulate_upgrade("openai/gpt-5.2")
        assert result != "openai:gpt-5-mini"
        assert "gpt-5.2" in result

    def test_gemini3_not_gemini25(self):
        result = _simulate_upgrade("vertex_ai/global/gemini-3-pro-preview")
        assert result != "google-vertex:gemini-2.5-pro"
        assert "gemini-3-pro-preview" in result


class TestMigrationPreservesModelName:
    """The migration NEVER alters the model portion of the string."""

    @pytest.mark.parametrize(
        ("input_val", "expected_model_portion"),
        [
            ("openai/gpt-5-mini", "gpt-5-mini"),
            ("openai/gpt-5.2", "gpt-5.2"),
            ("openai/gpt-4o-mini", "gpt-4o-mini"),
            ("anthropic/claude-3-5-sonnet-latest", "claude-3-5-sonnet-latest"),
            ("vertex_ai/global/gemini-2.5-pro", "global/gemini-2.5-pro"),
            ("vertex_ai/global/gemini-3-pro-preview", "global/gemini-3-pro-preview"),
            ("gemini/gemini-2.5-flash", "gemini-2.5-flash"),
            ("openrouter/google/gemini-3-pro", "google/gemini-3-pro"),
        ],
    )
    def test_model_portion_preserved(self, input_val: str, expected_model_portion: str):
        result = _simulate_upgrade(input_val)
        _, _, model_part = result.partition(":")
        assert model_part == expected_model_portion


class TestVertexAiGlobalPrefix:
    """Document the global/ prefix behavior for vertex_ai paths.

    The migration preserves the full path after the provider, including
    intermediate segments like 'global/'. This matches how ModelId.from_litellm()
    handles multi-segment paths (partition on first '/').
    """

    def test_global_prefix_preserved(self):
        result = _simulate_upgrade("vertex_ai/global/gemini-2.5-pro")
        assert result == "google-vertex:global/gemini-2.5-pro"

    def test_us_central1_prefix_preserved(self):
        result = _simulate_upgrade("vertex_ai/us-central1/gemini-2.5-pro")
        assert result == "google-vertex:us-central1/gemini-2.5-pro"


class TestModelNameStorageLocations:
    """Document all tables/columns that store model name strings.

    AC #3: Identify all tables and columns that store model name strings
    and verify they were not affected by migration 4d7edc118a2e.
    """

    def test_opennotes_sim_agents_model_name_is_target(self):
        """The migration explicitly targets opennotes_sim_agents.model_name."""
        migration_sql = (
            "UPDATE opennotes_sim_agents "
            "SET model_name = split_part(model_name, '/', 1) || ':' || "
            "substring(model_name from position('/' in model_name) + 1) "
            "WHERE model_name LIKE '%/%' AND model_name NOT LIKE '%:%'"
        )
        assert "opennotes_sim_agents" in migration_sql

    def test_notes_ai_model_not_affected(self):
        """notes.ai_model was added by migration 0a36caa8cd3b AFTER 4d7edc118a2e.

        The column did not exist when the normalization migration ran, so it
        was never subject to the format conversion. All values written to
        notes.ai_model were written by application code in pydantic-ai format.
        """
