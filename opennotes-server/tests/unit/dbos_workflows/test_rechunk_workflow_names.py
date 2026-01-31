"""Tests for rechunk workflow name constants."""

from __future__ import annotations


class TestWorkflowNameConstants:
    """Tests for workflow name constants used in external references."""

    def test_workflow_names_match_function_names(self) -> None:
        """Verify constants match actual function names for DBOSClient.enqueue()."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
            chunk_single_fact_check_workflow,
            rechunk_fact_check_workflow,
        )

        assert rechunk_fact_check_workflow.__name__ == RECHUNK_FACT_CHECK_WORKFLOW_NAME
        assert chunk_single_fact_check_workflow.__name__ == CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME

    def test_workflow_names_are_nonempty_strings(self) -> None:
        """Verify workflow names are valid non-empty strings."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        )

        assert isinstance(RECHUNK_FACT_CHECK_WORKFLOW_NAME, str)
        assert isinstance(CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME, str)
        assert len(RECHUNK_FACT_CHECK_WORKFLOW_NAME) > 0
        assert len(CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME) > 0

    def test_workflow_names_are_valid_identifiers(self) -> None:
        """Verify workflow names are valid Python identifiers."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        )

        assert RECHUNK_FACT_CHECK_WORKFLOW_NAME.isidentifier()
        assert CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME.isidentifier()

    def test_workflow_names_expected_values(self) -> None:
        """Verify workflow names have expected literal values for documentation."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        )

        assert RECHUNK_FACT_CHECK_WORKFLOW_NAME == "rechunk_fact_check_workflow"
        assert CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME == "chunk_single_fact_check_workflow"
