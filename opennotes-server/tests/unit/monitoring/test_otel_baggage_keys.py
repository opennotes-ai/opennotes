import pytest

from src.monitoring.otel import BAGGAGE_KEYS_TO_PROPAGATE


@pytest.mark.unit
class TestBaggageKeysToPropgate:
    def test_community_server_id_in_baggage_keys(self) -> None:
        assert "community_server_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_platform_channel_id_in_baggage_keys(self) -> None:
        assert "platform.channel_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_platform_user_id_in_baggage_keys(self) -> None:
        assert "platform.user_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_existing_keys_preserved(self) -> None:
        expected_keys = [
            "platform.user_id",
            "platform.type",
            "platform.scope",
            "platform.community_id",
            "request_id",
            "enduser.id",
            "user.username",
        ]
        for key in expected_keys:
            assert key in BAGGAGE_KEYS_TO_PROPAGATE
