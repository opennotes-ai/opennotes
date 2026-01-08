"""Import pipeline for fact-check datasets.

Provides streaming import, validation, and normalization of fact-check
datasets from sources like HuggingFace.
"""

from src.fact_checking.import_pipeline.importer import (
    ImportStats,
    import_fact_check_bureau,
    upsert_candidates,
    validate_and_normalize_batch,
)
from src.fact_checking.import_pipeline.promotion import bulk_promote_scraped, promote_candidate
from src.fact_checking.import_pipeline.rating_normalizer import normalize_rating
from src.fact_checking.import_pipeline.router import (
    ImportFactCheckBureauRequest,
    ImportFactCheckBureauResponse,
)
from src.fact_checking.import_pipeline.router import (
    router as import_router,
)
from src.fact_checking.import_pipeline.schemas import ClaimReviewRow, NormalizedCandidate
from src.fact_checking.import_pipeline.scrape_task import (
    enqueue_scrape_batch,
    scrape_candidate_content,
    scrape_url_content,
)

__all__ = [
    "ClaimReviewRow",
    "ImportFactCheckBureauRequest",
    "ImportFactCheckBureauResponse",
    "ImportStats",
    "NormalizedCandidate",
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
