from uuid import uuid4

from src.simulation.agent import build_queue_summary


def _make_request(content: str, status: str = "OPEN", notes: list | None = None) -> dict:
    return {
        "request_id": str(uuid4()),
        "content": content,
        "status": status,
        "notes": notes or [],
    }


def _make_note(
    summary: str,
    classification: str = "NOT_MISLEADING",
    status: str = "NEEDS_MORE_RATINGS",
) -> dict:
    return {
        "note_id": str(uuid4()),
        "summary": summary,
        "classification": classification,
        "status": status,
    }


class TestBuildQueueSummaryBrief:
    def test_brief_summary_with_requests_and_notes(self):
        requests = [
            _make_request("Claim about climate change"),
            _make_request("Vaccine misinformation post"),
        ]
        notes = [
            _make_note("This is accurate per NASA data"),
            _make_note("Missing context on trial results"),
        ]
        result = build_queue_summary(requests, notes)
        assert "2 content requests to write notes for:" in result
        assert "2 notes available to rate:" in result
        assert "climate change" in result.lower() or "Claim about climate change" in result
        assert "NASA" in result or "accurate" in result.lower()

    def test_brief_mode_limits_to_3_titles(self):
        requests = [_make_request(f"Request number {i}") for i in range(6)]
        notes = [_make_note(f"Note summary {i}") for i in range(5)]
        result = build_queue_summary(requests, notes, verbose=False)
        assert "6 content requests to write notes for:" in result
        assert "5 notes available to rate:" in result
        assert "and 3 more" in result
        assert "and 2 more" in result

    def test_brief_truncates_long_content(self):
        long_content = "A" * 200
        requests = [_make_request(long_content)]
        result = build_queue_summary(requests, [], verbose=False)
        assert len(long_content) > 50
        for line in result.splitlines():
            if "AAA" in line:
                title_part = line.strip().lstrip("- ")
                assert len(title_part) <= 60


class TestBuildQueueSummaryVerbose:
    def test_verbose_mode_shows_all_titles(self):
        requests = [_make_request(f"Request number {i}") for i in range(6)]
        notes = [_make_note(f"Note summary {i}") for i in range(5)]
        result = build_queue_summary(requests, notes, verbose=True)
        assert "6 content requests to write notes for:" in result
        assert "5 notes available to rate:" in result
        for i in range(6):
            assert f"Request number {i}" in result
        for i in range(5):
            assert f"Note summary {i}" in result
        assert "more" not in result.lower()

    def test_verbose_truncates_at_100_chars(self):
        long_content = "B" * 200
        requests = [_make_request(long_content)]
        result = build_queue_summary(requests, [], verbose=True)
        for line in result.splitlines():
            if "BBB" in line:
                title_part = line.strip().lstrip("- ")
                assert len(title_part) <= 110


class TestBuildQueueSummaryEdgeCases:
    def test_empty_queues(self):
        result = build_queue_summary([], [])
        assert "No content requests to write notes for." in result
        assert "No notes available to rate." in result

    def test_single_request(self):
        requests = [_make_request("Only request")]
        result = build_queue_summary(requests, [])
        assert "1 content request to write a note for:" in result
        assert "content requests" not in result

    def test_single_note_with_requests(self):
        requests = [_make_request("Some request")]
        notes = [_make_note("Only note")]
        result = build_queue_summary(requests, notes)
        assert "1 note available to rate:" in result
        assert "notes available" not in result

    def test_single_note_without_requests(self):
        notes = [_make_note("Only note")]
        result = build_queue_summary([], notes)
        assert "1 note available to rate" in result
        assert "No content requests" in result

    def test_exactly_3_items_no_more_suffix(self):
        requests = [_make_request(f"Req {i}") for i in range(3)]
        result = build_queue_summary(requests, [], verbose=False)
        assert "3 content requests to write notes for:" in result
        assert "more" not in result.lower()

    def test_returns_string(self):
        result = build_queue_summary([], [])
        assert isinstance(result, str)

    def test_notes_with_linked_request_notes_ignored(self):
        linked_note = _make_note("Linked note")
        requests = [_make_request("Has linked notes", notes=[linked_note])]
        result = build_queue_summary(requests, [], verbose=False)
        assert "1 content request to write a note for:" in result
        assert "Has linked notes" in result

    def test_no_requests_but_notes_cross_reference(self):
        notes = [_make_note("Some note"), _make_note("Another note")]
        result = build_queue_summary([], notes)
        assert "No content requests" in result
        assert "but" in result.lower()
        assert "notes available to rate" in result.lower()

    def test_no_requests_single_note_cross_reference(self):
        notes = [_make_note("Only note")]
        result = build_queue_summary([], notes)
        assert "No content requests" in result
        assert "but" in result.lower()
