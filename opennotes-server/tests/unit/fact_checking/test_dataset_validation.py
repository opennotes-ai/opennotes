import pytest

from src.fact_checking.dataset_models import FactCheckDataset


@pytest.mark.unit
class TestFactCheckDatasetModel:
    def test_model_has_correct_tablename(self):
        assert FactCheckDataset.__tablename__ == "fact_check_datasets"

    def test_slug_is_primary_key(self):
        pk_cols = [c.name for c in FactCheckDataset.__table__.primary_key.columns]
        assert pk_cols == ["slug"]

    def test_model_creates_with_required_fields(self):
        ds = FactCheckDataset(slug="snopes", display_name="Snopes")
        assert ds.slug == "snopes"
        assert ds.display_name == "Snopes"
        assert ds.description is None
        assert ds.source_url is None

    def test_enabled_defaults_to_true_at_db_level(self):
        col = FactCheckDataset.__table__.c.enabled
        assert col.server_default is not None
        assert str(col.server_default.arg) == "true"

    def test_created_at_has_server_default(self):
        col = FactCheckDataset.__table__.c.created_at
        assert col.server_default is not None


@pytest.mark.unit
class TestFactCheckItemDatasetFK:
    def test_dataset_name_has_foreign_key(self):
        from src.fact_checking.models import FactCheckItem

        col = FactCheckItem.__table__.c.dataset_name
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "fact_check_datasets.slug"
