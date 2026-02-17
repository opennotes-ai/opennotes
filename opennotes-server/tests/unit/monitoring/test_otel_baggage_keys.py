import pytest

from src.monitoring.otel import BAGGAGE_KEYS_TO_PROPAGATE


@pytest.mark.unit
class TestBaggageKeysToPropgate:
    def test_community_server_id_in_baggage_keys(self) -> None:
        assert "community_server_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_discord_channel_id_in_baggage_keys(self) -> None:
        assert "discord.channel_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_discord_guild_id_in_baggage_keys(self) -> None:
        assert "discord.guild_id" in BAGGAGE_KEYS_TO_PROPAGATE

    def test_existing_keys_preserved(self) -> None:
        expected_keys = [
            "discord.user_id",
            "discord.username",
            "discord.guild_id",
            "request_id",
            "enduser.id",
            "user.username",
        ]
        for key in expected_keys:
            assert key in BAGGAGE_KEYS_TO_PROPAGATE
