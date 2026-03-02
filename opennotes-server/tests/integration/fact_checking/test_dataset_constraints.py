import pytest
from sqlalchemy import text


@pytest.mark.integration
class TestDatasetConstraintsIntegration:
    @pytest.fixture
    async def seed_dataset(self, db):
        await db.execute(
            text(
                "INSERT INTO fact_check_datasets (slug, display_name) "
                "VALUES ('snopes', 'Snopes') ON CONFLICT DO NOTHING"
            )
        )
        await db.commit()

    async def test_valid_dataset_tag_insert_succeeds(self, db, seed_dataset):
        await db.execute(
            text(
                "INSERT INTO fact_check_items "
                "(dataset_name, dataset_tags, title, content, metadata) "
                "VALUES ('snopes', ARRAY['snopes'], 'Test', 'Content', '{}')"
            )
        )
        await db.commit()

    async def test_invalid_dataset_tag_rejected(self, db, seed_dataset):
        with pytest.raises(Exception, match="check_fact_check_items_dataset_tags_valid"):
            await db.execute(
                text(
                    "INSERT INTO fact_check_items "
                    "(dataset_name, dataset_tags, title, content, metadata) "
                    "VALUES ('snopes', ARRAY['nonexistent'], 'Test', 'Content', '{}')"
                )
            )

    async def test_fk_on_dataset_name_rejects_unknown_slug(self, db, seed_dataset):
        with pytest.raises(Exception, match="fk_fact_check_items_dataset_name"):
            await db.execute(
                text(
                    "INSERT INTO fact_check_items "
                    "(dataset_name, dataset_tags, title, content, metadata) "
                    "VALUES ('unknown_ds', ARRAY['snopes'], 'Test', 'Content', '{}')"
                )
            )

    async def test_empty_dataset_tags_passes_constraint(self, db, seed_dataset):
        await db.execute(
            text(
                "INSERT INTO fact_checked_item_candidates "
                "(source_url, claim_hash, title, dataset_name, dataset_tags) "
                "VALUES ('https://example.com', 'abcd1234abcd1234', 'Test', 'snopes', '{}')"
            )
        )
        await db.commit()

    async def test_candidate_invalid_tag_rejected(self, db, seed_dataset):
        with pytest.raises(Exception, match="check_candidates_dataset_tags_valid"):
            await db.execute(
                text(
                    "INSERT INTO fact_checked_item_candidates "
                    "(source_url, claim_hash, title, dataset_name, dataset_tags) "
                    "VALUES ('https://example.com', 'abcd1234abcd1234', 'Test', 'snopes', ARRAY['bogus'])"
                )
            )

    async def test_seed_data_includes_known_slugs(self, db):
        result = await db.execute(text("SELECT slug FROM fact_check_datasets ORDER BY slug"))
        slugs = [row[0] for row in result.fetchall()]
        for expected in ["fact-check", "misinformation", "politifact", "snopes"]:
            assert expected in slugs
