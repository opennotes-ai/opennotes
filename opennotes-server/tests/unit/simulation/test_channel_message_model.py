from src.simulation.models import SimChannelMessage


class TestSimChannelMessageModel:
    def test_can_import(self):
        assert SimChannelMessage is not None

    def test_tablename(self):
        assert SimChannelMessage.__tablename__ == "sim_channel_messages"

    def test_has_expected_columns(self):
        column_names = {c.name for c in SimChannelMessage.__table__.columns}
        assert "id" in column_names
        assert "simulation_run_id" in column_names
        assert "agent_instance_id" in column_names
        assert "message_text" in column_names

    def test_has_timestamp_columns(self):
        column_names = {c.name for c in SimChannelMessage.__table__.columns}
        assert "created_at" in column_names
        assert "updated_at" in column_names
