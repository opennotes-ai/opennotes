"""Tests for rechunk workflow name constants."""

from __future__ import annotations


class TestWorkflowNameConstants:
    """Tests for workflow name constants used in external references."""

    def test_workflow_names_derived_from_function_metadata(self) -> None:
        """Verify constants are derived from module and function names."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
            chunk_single_fact_check_workflow,
            rechunk_fact_check_workflow,
        )

        module = "src.dbos_workflows.rechunk_workflow"
        assert (
            f"{module}.{rechunk_fact_check_workflow.__name__}" == RECHUNK_FACT_CHECK_WORKFLOW_NAME
        )
        assert (
            f"{module}.{chunk_single_fact_check_workflow.__name__}"
            == CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME
        )

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

    def test_workflow_names_are_fully_qualified(self) -> None:
        """Verify workflow names are fully-qualified dotted paths."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        )

        assert "." in RECHUNK_FACT_CHECK_WORKFLOW_NAME
        assert "." in CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME
        for part in RECHUNK_FACT_CHECK_WORKFLOW_NAME.split("."):
            assert part.isidentifier()
        for part in CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME.split("."):
            assert part.isidentifier()

    def test_workflow_names_expected_values(self) -> None:
        """Verify workflow names have expected literal values for documentation."""
        from src.dbos_workflows.rechunk_workflow import (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME,
            RECHUNK_FACT_CHECK_WORKFLOW_NAME,
        )

        assert (
            RECHUNK_FACT_CHECK_WORKFLOW_NAME
            == "src.dbos_workflows.rechunk_workflow.rechunk_fact_check_workflow"
        )
        assert (
            CHUNK_SINGLE_FACT_CHECK_WORKFLOW_NAME
            == "src.dbos_workflows.rechunk_workflow.chunk_single_fact_check_workflow"
        )
