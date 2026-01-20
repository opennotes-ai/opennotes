# API Migration Notes

This document tracks breaking changes and migration guidance for API consumers.

## 2026-01-20: TRACE_SAMPLE_RATE Environment Variable Renamed

### Change Summary

The environment variable `TRACE_SAMPLE_RATE` has been renamed to `TRACING_SAMPLE_RATE` for consistency with the `ENABLE_TRACING` variable.

**IMPORTANT**: The default value has been restored to `0.1` (10% sampling). If you were relying on the temporary default of `1.0` (100% sampling), you will need to explicitly set `TRACING_SAMPLE_RATE=1.0`.

### Backwards Compatibility

The old `TRACE_SAMPLE_RATE` environment variable is still supported but deprecated. A deprecation warning will be logged when the old variable is used. Update your configuration to use `TRACING_SAMPLE_RATE` before the next major release.

### Migration Guide

**Before:**
```bash
export TRACE_SAMPLE_RATE=0.2
```

**After:**
```bash
export TRACING_SAMPLE_RATE=0.2
```

### Default Value

The default sampling rate is `0.1` (10% of traces). This is appropriate for production environments to control tracing costs. For development or debugging, set `TRACING_SAMPLE_RATE=1.0` to capture all traces.

---

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
