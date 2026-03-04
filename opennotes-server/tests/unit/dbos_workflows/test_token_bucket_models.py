from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool, TokenPoolWorker


class TestTokenPoolModel:
    def test_tablename(self):
        assert TokenPool.__tablename__ == "token_pools"

    def test_primary_key_is_pool_name(self):
        pk_cols = [c.name for c in TokenPool.__table__.primary_key.columns]
        assert pk_cols == ["pool_name"]


class TestTokenHoldModel:
    def test_tablename(self):
        assert TokenHold.__tablename__ == "token_holds"

    def test_has_unique_constraint(self):
        constraint_names = [c.name for c in TokenHold.__table__.constraints if hasattr(c, "name")]
        assert "uq_token_hold_pool_workflow" in constraint_names

    def test_pool_name_is_foreign_key(self):
        col = TokenHold.__table__.c.pool_name
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert str(fks[0].target_fullname) == "token_pools.pool_name"


class TestTokenPoolWorkerModel:
    def test_tablename(self):
        assert TokenPoolWorker.__tablename__ == "token_pool_workers"

    def test_has_unique_constraint(self):
        constraint_names = [
            c.name for c in TokenPoolWorker.__table__.constraints if hasattr(c, "name")
        ]
        assert "uq_token_pool_worker" in constraint_names

    def test_pool_name_is_foreign_key(self):
        col = TokenPoolWorker.__table__.c.pool_name
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert str(fks[0].target_fullname) == "token_pools.pool_name"

    def test_has_worker_id_column(self):
        assert "worker_id" in TokenPoolWorker.__table__.c

    def test_has_capacity_contribution_column(self):
        assert "capacity_contribution" in TokenPoolWorker.__table__.c

    def test_has_last_heartbeat_column(self):
        assert "last_heartbeat" in TokenPoolWorker.__table__.c

    def test_has_registered_at_column(self):
        assert "registered_at" in TokenPoolWorker.__table__.c

    def test_pool_name_fk_has_cascade_delete(self):
        col = TokenPoolWorker.__table__.c.pool_name
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].ondelete == "CASCADE"


class TestTokenHoldIndexAndFK:
    def test_released_at_has_index(self):
        col = TokenHold.__table__.c.released_at
        assert col.index is True

    def test_pool_name_fk_has_cascade_delete(self):
        col = TokenHold.__table__.c.pool_name
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].ondelete == "CASCADE"
