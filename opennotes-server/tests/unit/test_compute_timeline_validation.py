from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.simulation.analysis import compute_timeline


@pytest.mark.asyncio
async def test_compute_timeline_rejects_invalid_bucket_size():
    mock_instance = MagicMock(user_profile_id=uuid4())

    with patch(
        "src.simulation.analysis._get_agent_instances",
        new_callable=AsyncMock,
        return_value=[mock_instance],
    ):
        mock_db = AsyncMock()
        mock_run = MagicMock()
        mock_scalar_result = MagicMock()
        mock_scalar_result.scalar_one.return_value = mock_run
        mock_db.execute.return_value = mock_scalar_result

        with pytest.raises(ValueError, match="Invalid bucket_size"):
            await compute_timeline(uuid4(), mock_db, bucket_size="invalid")
