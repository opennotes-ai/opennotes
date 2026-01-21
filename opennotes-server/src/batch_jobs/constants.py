"""
Shared constants for batch job types.

Centralizes job type strings to prevent drift between services
and ensure consistent naming across the codebase.
"""

IMPORT_JOB_TYPE = "import:fact_check_bureau"
SCRAPE_JOB_TYPE = "scrape:candidates"
PROMOTION_JOB_TYPE = "promote:candidates"
BULK_APPROVAL_JOB_TYPE = "approve:candidates"

RECHUNK_FACT_CHECK_JOB_TYPE = "rechunk:fact_check"
RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE = "rechunk:previously_seen"

DEFAULT_SCRAPE_CONCURRENCY = 10  # Max concurrent URL scrapes
SCRAPE_URL_TIMEOUT_SECONDS = 60  # Per-URL timeout

__all__ = [
    "BULK_APPROVAL_JOB_TYPE",
    "DEFAULT_SCRAPE_CONCURRENCY",
    "IMPORT_JOB_TYPE",
    "PROMOTION_JOB_TYPE",
    "RECHUNK_FACT_CHECK_JOB_TYPE",
    "RECHUNK_PREVIOUSLY_SEEN_JOB_TYPE",
    "SCRAPE_JOB_TYPE",
    "SCRAPE_URL_TIMEOUT_SECONDS",
]
