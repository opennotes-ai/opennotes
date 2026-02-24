from src.dbos_workflows.token_bucket.models import TokenHold, TokenPool


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
