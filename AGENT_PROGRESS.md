# Task 986 Parallel Agent Progress

## Status Tracker
| Task | Status | Agent |
|------|--------|-------|
| 986.01 | Done | @backend-developer |
| 986.02 | Done | @backend-developer |
| 986.03 | Done | @backend-developer |
| 986.04 | Pending | - |
| 986.05 | Pending | - |
| 986.06 | Done | @backend-developer |
| 986.07 | Pending | - |
| 986.08 | Done | @backend-developer |
| 986.09 | Pending | - |
| 986.10 | Pending | - |
| 986.11 | Pending | - |
| 986.12 | Done | @backend-developer |

## Agent Notes
Each agent will append their completion summary below.

---

### 986.02 - Fix downgrade idempotency in fix_preexisting_schema_drift.py
Replaced `op.drop_index()` with `DROP INDEX IF EXISTS` using raw SQL via `conn.execute(sa.text(...))`.
This matches the upgrade's `IF NOT EXISTS` pattern for idempotent migrations.

### 986.08 - Fix state transition ordering in service.py start_job()
Reordered start_job() to call start_tracking() before setting status/started_at.
Added try/except around flush() with rollback to stop_tracking() on failure.
### 986.01 - Fix migration server_default quoting
Fixed JSONB default to `sa.text("'{}'::jsonb")`, status default to `sa.text("'pending'")`, and removed duplicate `ix_batch_jobs_id` index (PK already indexed).

### 986.03 - Fix lock release race condition in rechunk_service.py
Removed dead code (`if job is None: raise RuntimeError`) after start_job() calls.
Added fail_job() handling when TaskIQ dispatch fails to mark job FAILED and release lock.

### 986.06 - Fix OpenAPI schema mismatches
Added `responses` definitions for 404/409 error codes to batch_jobs/router.py (get_batch_job, get_batch_job_progress, cancel_batch_job) and chunk_router.py (get_rechunk_job_status, cancel_rechunk_job).
Import endpoint already had correct 201 status code. Regenerated OpenAPI spec and TypeScript types.

### 986.12 - Add claim_hash field validator in import schemas
Added pattern validator `^[0-9a-f]{16}$` to NormalizedCandidate.claim_hash field.
Added unit test for pattern validation. OpenAPI/TS regeneration not needed (internal schema).

### 986.05 - Fix missing transaction rollback in rechunk_tasks.py
Added error aggregation (item_errors list), wrapped update_progress calls in try/except with warning log,
and added explicit rollback in failure handlers before logging errors.
