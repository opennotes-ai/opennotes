"""Unit tests for fact-check CLI commands."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.batch_jobs.models import BatchJob
from src.cli.fact_check import candidates, fact_check


@pytest.fixture
def cli_runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


def _create_mock_job() -> MagicMock:
    """Create a mock BatchJob."""
    mock_job = MagicMock(spec=BatchJob)
    mock_job.id = "test-job-id"
    mock_job.status = "pending"
    return mock_job


def _create_mock_session_maker(mock_session: AsyncMock) -> MagicMock:
    """Create a mock session maker that returns the mock session."""

    class MockContextManager:
        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(self, *args: object) -> None:
            pass

    maker = MagicMock()
    maker.return_value = MockContextManager()
    return maker


class TestFactCheckGroup:
    """Tests for the fact-check command group."""

    def test_fact_check_group_exists(self, cli_runner: CliRunner) -> None:
        """Test that fact-check command group is accessible."""
        result = cli_runner.invoke(fact_check, ["--help"])
        assert result.exit_code == 0
        assert "Fact-check related operations" in result.output

    def test_candidates_subgroup_exists(self, cli_runner: CliRunner) -> None:
        """Test that candidates subgroup is accessible."""
        result = cli_runner.invoke(candidates, ["--help"])
        assert result.exit_code == 0
        assert "Manage fact-check candidates" in result.output


class TestImportCommand:
    """Tests for the import command."""

    def test_import_help(self, cli_runner: CliRunner) -> None:
        """Test import command help text."""
        result = cli_runner.invoke(candidates, ["import", "--help"])
        assert result.exit_code == 0
        assert "Import fact-check candidates" in result.output
        assert "--batch-size" in result.output
        assert "--dry-run" in result.output
        assert "--wait" in result.output
        assert "--verbose" in result.output

    def test_import_requires_source(self, cli_runner: CliRunner) -> None:
        """Test that import requires a source argument."""
        result = cli_runner.invoke(candidates, ["import"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_import_invalid_source(self, cli_runner: CliRunner) -> None:
        """Test that import rejects invalid source."""
        result = cli_runner.invoke(candidates, ["import", "invalid-source"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_import_valid_source_accepted(self, cli_runner: CliRunner) -> None:
        """Test that fact-check-bureau is accepted as a valid source."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_import_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates, ["import", "fact-check-bureau"], catch_exceptions=False
            )

            assert result.exit_code == 0
            assert "Starting import" in result.output
            assert "Created job" in result.output
            mock_service.start_import_job.assert_called_once()

    def test_import_with_batch_size(self, cli_runner: CliRunner) -> None:
        """Test import with custom batch size."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_import_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["import", "fact-check-bureau", "--batch-size", "500"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_service.start_import_job.assert_called_once_with(
                batch_size=500,
                dry_run=False,
            )

    def test_import_dry_run(self, cli_runner: CliRunner) -> None:
        """Test import with dry-run flag."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_import_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["import", "fact-check-bureau", "--dry-run"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_service.start_import_job.assert_called_once_with(
                batch_size=1000,
                dry_run=True,
            )


class TestScrapeContentCommand:
    """Tests for the scrape-content command."""

    def test_scrape_content_help(self, cli_runner: CliRunner) -> None:
        """Test scrape-content command help text."""
        result = cli_runner.invoke(candidates, ["scrape-content", "--help"])
        assert result.exit_code == 0
        assert "Scrape content" in result.output
        assert "--batch-size" in result.output
        assert "--dry-run" in result.output
        assert "--wait" in result.output

    def test_scrape_content_calls_service(self, cli_runner: CliRunner) -> None:
        """Test scrape-content calls the service correctly."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(candidates, ["scrape-content"], catch_exceptions=False)

            assert result.exit_code == 0
            assert "Starting content scraping" in result.output
            mock_service.start_scrape_job.assert_called_once_with(
                batch_size=1000,
                dry_run=False,
            )

    def test_scrape_content_with_options(self, cli_runner: CliRunner) -> None:
        """Test scrape-content with custom options."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_scrape_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["scrape-content", "--batch-size", "200", "--dry-run"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_service.start_scrape_job.assert_called_once_with(
                batch_size=200,
                dry_run=True,
            )


class TestPromoteCommand:
    """Tests for the promote command."""

    def test_promote_help(self, cli_runner: CliRunner) -> None:
        """Test promote command help text."""
        result = cli_runner.invoke(candidates, ["promote", "--help"])
        assert result.exit_code == 0
        assert "Promote scraped candidates" in result.output
        assert "--batch-size" in result.output
        assert "--dry-run" in result.output
        assert "--wait" in result.output

    def test_promote_calls_service(self, cli_runner: CliRunner) -> None:
        """Test promote calls the service correctly."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(candidates, ["promote"], catch_exceptions=False)

            assert result.exit_code == 0
            assert "Starting candidate promotion" in result.output
            mock_service.start_promotion_job.assert_called_once_with(
                batch_size=1000,
                dry_run=False,
            )

    def test_promote_with_all_options(self, cli_runner: CliRunner) -> None:
        """Test promote with all options."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_promotion_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["promote", "-b", "50", "-n", "-v"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            assert "DRY RUN" in result.output
            mock_service.start_promotion_job.assert_called_once_with(
                batch_size=50,
                dry_run=True,
            )


class TestCommonOptions:
    """Tests for common batch options behavior."""

    def test_short_options_work(self, cli_runner: CliRunner) -> None:
        """Test that short option flags work correctly."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_import_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["import", "fact-check-bureau", "-b", "100", "-n", "-v"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_service.start_import_job.assert_called_once_with(
                batch_size=100,
                dry_run=True,
            )

    def test_default_batch_size(self, cli_runner: CliRunner) -> None:
        """Test that default batch size is 1000."""
        mock_job = _create_mock_job()
        mock_session = AsyncMock()
        mock_maker = _create_mock_session_maker(mock_session)

        mock_service = AsyncMock()
        mock_service.start_import_job = AsyncMock(return_value=mock_job)

        with (
            patch("src.database.get_session_maker", return_value=mock_maker),
            patch(
                "src.batch_jobs.import_service.ImportBatchJobService",
                return_value=mock_service,
            ),
            patch("src.cli.fact_check._setup_logging"),
        ):
            result = cli_runner.invoke(
                candidates,
                ["import", "fact-check-bureau"],
                catch_exceptions=False,
            )

            assert result.exit_code == 0
            mock_service.start_import_job.assert_called_once_with(
                batch_size=1000,
                dry_run=False,
            )
