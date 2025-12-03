import logging

import pytest


@pytest.mark.asyncio
async def test_monkey_patch_logging(caplog):
    """Test that the monkey patch logging message appears when scoring runs"""
    from src.scoring_adapter import _apply_scoring_threshold_monkey_patch

    with caplog.at_level(logging.INFO):
        _apply_scoring_threshold_monkey_patch()

        log_messages = [record.message for record in caplog.records]

        # Should see either the patch application message or the environment message
        relevant_logs = [
            msg
            for msg in log_messages
            if "scoring threshold" in msg.lower() or "monkey patch" in msg.lower()
        ]

        assert len(relevant_logs) > 0, f"Expected monkey patch log messages, got: {log_messages}"
        print(f"✓ Monkey patch log messages: {relevant_logs}")
