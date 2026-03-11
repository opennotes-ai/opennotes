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

    def test_has_composite_index_on_run_created(self):
        indexes = {idx.name: idx for idx in SimChannelMessage.__table__.indexes}
        idx = indexes.get("idx_sim_channel_messages_run_created")
        assert idx is not None, "Composite index idx_sim_channel_messages_run_created missing"
        col_names = [c.name for c in idx.columns]
        assert col_names == ["simulation_run_id", "created_at"]

    def test_simulation_run_id_fk_cascades(self):
        col = SimChannelMessage.__table__.c.simulation_run_id
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk.target_fullname == "simulation_runs.id"
        assert fk.ondelete == "CASCADE"

    def test_agent_instance_id_fk_cascades(self):
        col = SimChannelMessage.__table__.c.agent_instance_id
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        fk = fks[0]
        assert fk.target_fullname == "sim_agent_instances.id"
        assert fk.ondelete == "CASCADE"
