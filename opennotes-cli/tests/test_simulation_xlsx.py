from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from opennotes_cli.cli import cli


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _make_csrf_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _make_detailed_response(simulation_id: str) -> MagicMock:
    body = {
        "data": [
            {
                "type": "simulation-detailed-notes",
                "id": "note-001",
                "attributes": {
                    "note_id": "note-001",
                    "summary": "Claim is misleading due to cherry-picked statistics",
                    "classification": "MISINFORMATION",
                    "status": "scored",
                    "helpfulness_score": 0.85,
                    "author_agent_name": "Skeptic",
                    "author_agent_instance_id": "skeptic-1",
                    "request_id": "req-001",
                    "created_at": "2026-03-01T10:00:00Z",
                    "ratings": [
                        {
                            "rater_agent_name": "Optimist",
                            "rater_agent_instance_id": "optimist-1",
                            "helpfulness_level": "HELPFUL",
                            "created_at": "2026-03-01T10:10:00Z",
                        }
                    ],
                },
            },
            {
                "type": "simulation-detailed-notes",
                "id": "note-002",
                "attributes": {
                    "note_id": "note-002",
                    "summary": "Source is reliable and well-cited",
                    "classification": "ACCURATE",
                    "status": "scored",
                    "helpfulness_score": 0.72,
                    "author_agent_name": "Optimist",
                    "author_agent_instance_id": "optimist-1",
                    "request_id": "req-002",
                    "created_at": "2026-03-01T10:05:00Z",
                    "ratings": [
                        {
                            "rater_agent_name": "Skeptic",
                            "rater_agent_instance_id": "skeptic-1",
                            "helpfulness_level": "SOMEWHAT_HELPFUL",
                            "created_at": "2026-03-01T10:15:00Z",
                        }
                    ],
                },
            },
        ],
        "links": {},
        "meta": {
            "count": 2,
            "request_variance": {
                "requests": [
                    {
                        "request_id": "req-001",
                        "content": "https://example.com/article-1",
                        "content_type": "url",
                        "note_count": 3,
                        "variance_score": 0.92,
                    },
                    {
                        "request_id": "req-002",
                        "content": "Some user-submitted text",
                        "content_type": "text",
                        "note_count": 2,
                        "variance_score": 0.45,
                    },
                ],
                "total_requests": 2,
            },
        },
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


SIM_ID = "sim-xlsx-001"


def _make_xlsx_client() -> MagicMock:
    csrf_resp = _make_csrf_response()
    detail_resp = _make_detailed_response(SIM_ID)
    mock_client = MagicMock()
    mock_client.get.side_effect = [csrf_resp, detail_resp]
    mock_client.cookies = MagicMock()
    mock_client.cookies.get.return_value = "test-csrf"
    return mock_client


class TestXlsxRequiresDetailed:
    def test_xlsx_without_detailed_errors(self, runner: CliRunner) -> None:
        result = runner.invoke(
            cli, ["--local", "simulation", "analysis", "--format", "xlsx", SIM_ID]
        )
        assert result.exit_code != 0
        assert "requires --detailed" in result.output or "requires --detailed" in (result.output + str(result.exception or ""))


class TestXlsxOutput:
    def test_xlsx_creates_file(self, runner: CliRunner, tmp_path: object) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test-output.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                result = runner.invoke(
                    cli,
                    [
                        "--local",
                        "simulation",
                        "analysis",
                        "--detailed",
                        "--format",
                        "xlsx",
                        "--output",
                        output_file,
                        SIM_ID,
                    ],
                )
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            assert os.path.exists(output_file)

    def test_xlsx_default_filename(self, runner: CliRunner) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                old_cwd = os.getcwd()
                try:
                    os.chdir(tmpdir)
                    result = runner.invoke(
                        cli,
                        [
                            "--local",
                            "simulation",
                            "analysis",
                            "--detailed",
                            "--format",
                            "xlsx",
                            SIM_ID,
                        ],
                    )
                finally:
                    os.chdir(old_cwd)
            assert result.exit_code == 0
            expected_file = os.path.join(tmpdir, f"simulation-{SIM_ID}-detailed.xlsx")
            assert os.path.exists(expected_file)


class TestXlsxNotesSheet:
    def test_notes_sheet_has_correct_headers(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Notes"]
            headers = [cell.value for cell in ws[1]]
            assert "Note ID" in headers
            assert "Summary" in headers
            assert "Classification" in headers
            assert "Status" in headers
            assert "Helpfulness Score" in headers
            assert "Author Agent" in headers
            assert "Request ID" in headers
            assert "Created At" in headers

    def test_notes_sheet_has_data_rows(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Notes"]
            assert ws.max_row == 3
            assert ws.cell(row=2, column=1).value == "note-001"
            assert ws.cell(row=3, column=1).value == "note-002"


class TestXlsxRatingsSheet:
    def test_ratings_sheet_has_correct_headers(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Ratings"]
            headers = [cell.value for cell in ws[1]]
            assert "Note ID" in headers
            assert "Note Summary" in headers
            assert "Rater Agent" in headers
            assert "Helpfulness Level" in headers
            assert "Created At" in headers

    def test_ratings_sheet_truncates_summary(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Ratings"]
            summary_val = ws.cell(row=2, column=2).value
            assert len(summary_val) <= 50


class TestXlsxRequestsSheet:
    def test_requests_sheet_has_correct_headers(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Requests"]
            headers = [cell.value for cell in ws[1]]
            assert "Request ID" in headers
            assert "Content" in headers
            assert "Content Type" in headers
            assert "Note Count" in headers
            assert "Variance Score" in headers

    def test_requests_sheet_has_data(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Requests"]
            assert ws.max_row == 3
            assert ws.cell(row=2, column=1).value == "req-001"
            assert ws.cell(row=2, column=4).value == 3
            assert ws.cell(row=2, column=5).value == 0.92


class TestXlsxOpensCorrectly:
    def test_workbook_has_three_sheets(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            assert wb.sheetnames == ["Notes", "Ratings", "Requests"]

    def test_columns_have_width(self, runner: CliRunner) -> None:
        import tempfile

        from openpyxl import load_workbook

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "test.xlsx")
            mock_client = _make_xlsx_client()
            with patch("opennotes_cli.cli.httpx.Client", return_value=mock_client):
                runner.invoke(
                    cli,
                    ["--local", "simulation", "analysis", "--detailed", "--format", "xlsx", "--output", output_file, SIM_ID],
                )
            wb = load_workbook(output_file)
            ws = wb["Notes"]
            a_width = ws.column_dimensions["A"].width
            assert a_width > 0


class TestOutputFlag:
    def test_output_flag_in_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["simulation", "analysis", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output
