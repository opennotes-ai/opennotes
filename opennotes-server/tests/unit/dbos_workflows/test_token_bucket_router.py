from datetime import UTC, datetime

from src.dbos_workflows.token_bucket.schemas import TokenHoldDetail, TokenPoolStatus


class TestTokenPoolStatusSchema:
    def test_from_dict(self):
        status = TokenPoolStatus(
            pool_name="default",
            capacity=12,
            available=7,
            active_hold_count=2,
            utilization_pct=41.7,
        )
        assert status.pool_name == "default"
        assert status.capacity == 12
        assert status.available == 7
        assert status.utilization_pct == 41.7

    def test_from_attributes(self):
        class FakePool:
            pool_name = "llm"
            capacity = 10
            available = 3
            active_hold_count = 4
            utilization_pct = 70.0

        status = TokenPoolStatus.model_validate(FakePool(), from_attributes=True)
        assert status.pool_name == "llm"
        assert status.active_hold_count == 4


class TestTokenHoldDetailSchema:
    def test_from_dict(self):
        detail = TokenHoldDetail(
            workflow_id="wf-123",
            weight=5,
            acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        assert detail.workflow_id == "wf-123"
        assert detail.weight == 5

    def test_serialization_roundtrip(self):
        detail = TokenHoldDetail(
            workflow_id="wf-456",
            weight=3,
            acquired_at=datetime(2026, 6, 15, 12, 30, 0, tzinfo=UTC),
        )
        data = detail.model_dump()
        restored = TokenHoldDetail(**data)
        assert restored.workflow_id == detail.workflow_id
        assert restored.weight == detail.weight
        assert restored.acquired_at == detail.acquired_at
