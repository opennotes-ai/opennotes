"""Import pipeline for fact-check datasets.

Provides streaming import, validation, and normalization of fact-check
datasets from sources like HuggingFace.

Note: Import operations now run asynchronously via BatchJob infrastructure.
Use POST /api/v1/fact-checking/import/fact-check-bureau to start an import job,
and poll GET /api/v1/batch-jobs/{job_id} for status.
"""

from src.fact_checking.import_pipeline.importer import (
    ImportStats,
    RowCountMismatchError,
    import_fact_check_bureau,
    upsert_candidates,
    validate_and_normalize_batch,
)
from src.fact_checking.import_pipeline.promotion import bulk_promote_scraped, promote_candidate
from src.fact_checking.import_pipeline.rating_normalizer import normalize_rating
from src.fact_checking.import_pipeline.router import (
    ImportFactCheckBureauRequest,
)
from src.fact_checking.import_pipeline.router import (
    router as import_router,
)
from src.fact_checking.import_pipeline.schemas import ClaimReviewRow, NormalizedCandidate
from src.fact_checking.import_pipeline.scrape_tasks import (
    enqueue_scrape_batch,
    scrape_candidate_content,
    scrape_url_content,
)

__all__ = [
    "ClaimReviewRow",
    "ImportFactCheckBureauRequest",
    "ImportStats",
    "NormalizedCandidate",
    "RowCountMismatchError",
    "bulk_promote_scraped",
    "enqueue_scrape_batch",
    "import_fact_check_bureau",
    "import_router",
    "normalize_rating",
    "promote_candidate",
    "scrape_candidate_content",
    "scrape_url_content",
    "upsert_candidates",
    "validate_and_normalize_batch",
]
