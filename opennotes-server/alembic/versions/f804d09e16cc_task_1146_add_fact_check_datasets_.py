"""task-1146: add fact_check_datasets reference table

Create fact_check_datasets table as a source-of-truth registry for dataset
identifiers. Add validate_dataset_tags() SQL function and CHECK constraints
on fact_check_items, fact_checked_item_candidates, and monitored_channels.
Add FK from fact_check_items.dataset_name to fact_check_datasets.slug.

Revision ID: f804d09e16cc
Revises: 55d3b5d409c0
Create Date: 2026-03-02 11:59:53.864299

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f804d09e16cc"
down_revision: str | Sequence[str] | None = "55d3b5d409c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_DATASETS = [
    ("snopes", "Snopes"),
    ("politifact", "PolitiFact"),
    ("fact-check", "Fact Check"),
    ("misinformation", "Misinformation"),
]


def upgrade() -> None:
    op.create_table(
        "fact_check_datasets",
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("slug"),
    )

    conn = op.get_bind()

    for slug, display_name in SEED_DATASETS:
        conn.execute(
            sa.text(
                "INSERT INTO fact_check_datasets (slug, display_name) "
                "VALUES (:slug, :display_name) ON CONFLICT DO NOTHING"
            ),
            {"slug": slug, "display_name": display_name},
        )

    conn.execute(
        sa.text(
            "INSERT INTO fact_check_datasets (slug, display_name) "
            "SELECT DISTINCT tag, tag "
            "FROM fact_check_items, unnest(dataset_tags) AS tag "
            "WHERE tag NOT IN (SELECT slug FROM fact_check_datasets) "
            "ON CONFLICT DO NOTHING"
        )
    )

    conn.execute(
        sa.text(
            "INSERT INTO fact_check_datasets (slug, display_name) "
            "SELECT DISTINCT dataset_name, dataset_name "
            "FROM fact_check_items "
            "WHERE dataset_name NOT IN (SELECT slug FROM fact_check_datasets) "
            "ON CONFLICT DO NOTHING"
        )
    )

    conn.execute(
        sa.text(
            "INSERT INTO fact_check_datasets (slug, display_name) "
            "SELECT DISTINCT tag, tag "
            "FROM fact_checked_item_candidates, unnest(dataset_tags) AS tag "
            "WHERE tag NOT IN (SELECT slug FROM fact_check_datasets) "
            "ON CONFLICT DO NOTHING"
        )
    )

    conn.execute(
        sa.text(
            "INSERT INTO fact_check_datasets (slug, display_name) "
            "SELECT DISTINCT tag, tag "
            "FROM monitored_channels, unnest(dataset_tags) AS tag "
            "WHERE tag NOT IN (SELECT slug FROM fact_check_datasets) "
            "ON CONFLICT DO NOTHING"
        )
    )

    op.execute(
        sa.text("""
            CREATE FUNCTION validate_dataset_tags(tags text[]) RETURNS boolean AS $$
                SELECT bool_and(t = ANY(SELECT slug FROM fact_check_datasets))
                FROM unnest(tags) AS t;
            $$ LANGUAGE sql STABLE
        """)
    )

    op.create_check_constraint(
        "check_fact_check_items_dataset_tags_valid",
        "fact_check_items",
        sa.text("validate_dataset_tags(dataset_tags)"),
    )

    op.create_check_constraint(
        "check_candidates_dataset_tags_valid",
        "fact_checked_item_candidates",
        sa.text("validate_dataset_tags(dataset_tags)"),
    )

    op.create_check_constraint(
        "check_monitored_channels_dataset_tags_valid",
        "monitored_channels",
        sa.text("validate_dataset_tags(dataset_tags)"),
    )

    op.create_foreign_key(
        "fk_fact_check_items_dataset_name",
        "fact_check_items",
        "fact_check_datasets",
        ["dataset_name"],
        ["slug"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_fact_check_items_dataset_name", "fact_check_items", type_="foreignkey")

    op.drop_constraint(
        "check_monitored_channels_dataset_tags_valid",
        "monitored_channels",
        type_="check",
    )
    op.drop_constraint(
        "check_candidates_dataset_tags_valid",
        "fact_checked_item_candidates",
        type_="check",
    )
    op.drop_constraint(
        "check_fact_check_items_dataset_tags_valid",
        "fact_check_items",
        type_="check",
    )

    op.execute(sa.text("DROP FUNCTION IF EXISTS validate_dataset_tags(text[])"))

    op.drop_table("fact_check_datasets")
