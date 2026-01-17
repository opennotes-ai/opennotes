# API Migration Notes

This document tracks breaking changes and migration guidance for API consumers.

## 2026-01-16: Batch Job Concurrency Response Code Change

### Change Summary

The HTTP status code returned when attempting to start a batch job while another is already in progress has been corrected from `409 Conflict` to `429 Too Many Requests`.

### Affected Endpoints

- `POST /api/v1/fact-checking/import/fact-check-bureau`
- `POST /api/v1/fact-checking/import/scrape-candidates`
- `POST /api/v1/fact-checking/import/promote-candidates`
- `POST /api/v1/chunks/fact-check/rechunk`
- `POST /api/v1/chunks/previously-seen/rechunk`

### Reason for Change

The `DistributedRateLimitMiddleware` handles concurrent job prevention and returns `429 Too Many Requests` when a job of the same type is already running. The previous documentation incorrectly stated `409 Conflict` would be returned.

This is semantically correct because:
- `429 Too Many Requests` indicates rate limiting, which is what the middleware enforces
- `409 Conflict` is typically used for resource state conflicts (e.g., optimistic locking failures)

### Migration Guide

API clients should update their error handling:

**Before:**
```python
if response.status_code == 409:
    # Job already in progress, retry later
```

**After:**
```python
if response.status_code == 429:
    # Job already in progress, retry later
    # Check Retry-After header if present
```

### Note on 409 Usage

The `409 Conflict` status code is still used correctly in the following scenarios:
- `DELETE /api/v1/chunks/jobs/{job_id}` - When attempting to cancel a job that is in a terminal state (completed, failed, or cancelled)
- `DELETE /api/v1/batch-jobs/{job_id}` - Same as above

These represent actual state conflicts, not rate limiting.
