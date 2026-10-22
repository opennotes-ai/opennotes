"""Add page_count and extracted_metadata to url_scan_pdf_archives.

Revision ID: task1657_28
Revises: task1657_14
Create Date: 2026-05-22

TASK-1657.28 adds structured extraction output columns to
``url_scan_pdf_archives`` so the pdf_extract step can persist per-page
text and document-level PDF metadata alongside the full-text ``html`` field.

New columns:
- ``page_count`` INTEGER — total pages extracted from the PDF (NULL for rows
  written before this migration)
- ``extracted_metadata`` JSONB — document-level PDF metadata dict
  (author, title, creator, …)

Both columns are nullable so existing archive rows remain valid.

Idempotency: ``ADD COLUMN IF NOT EXISTS`` guards prevent errors on re-run.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "task1657_28"
down_revision: str | Sequence[str] | None = "task1657_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.url_scan_pdf_archives
            ADD COLUMN IF NOT EXISTS page_count INTEGER,
            ADD COLUMN IF NOT EXISTS extracted_metadata JSONB
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public.url_scan_pdf_archives DROP COLUMN IF EXISTS extracted_metadata")
    op.execute("ALTER TABLE public.url_scan_pdf_archives DROP COLUMN IF EXISTS page_count")
