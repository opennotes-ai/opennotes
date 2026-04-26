-- Vibecheck Supabase schema (TASK-1473.04)
--
-- Two contracts coexist here:
--
-- 1. `vibecheck_analyses` — the legacy 72h sidebar cache (TASK-1471), keyed
--    by normalized URL. Service-role-only after the lockdown below; the
--    public policy that allowed anon writes is dropped.
--
-- 2. The async-pipeline trio (TASK-1473): `vibecheck_jobs` (lifecycle +
--    section state), `vibecheck_scrapes` (persisted scrape bundles for
--    retry resumption), `vibecheck_job_utterances` (per-job utterance
--    cache).
--
-- All vibecheck tables are RLS-locked (ENABLE + FORCE) with no policies for
-- anon or authenticated; only service_role bypasses RLS. All access flows
-- through vibecheck-server using SUPABASE_SERVICE_ROLE_KEY (TASK-1473.02).
--
-- Idempotency: every CREATE uses `IF NOT EXISTS`; every CREATE FUNCTION
-- uses `OR REPLACE`; every cron schedule is unscheduled-then-rescheduled in
-- one statement so re-running this file leaves a clean slate.

-- =========================================================================
-- Extensions
-- =========================================================================

-- pg_cron must be allowlisted in the Supabase dashboard before this runs
-- (TASK-1473.02 §10.1). The `IF NOT EXISTS` keeps the file re-runnable
-- when the extension is already present.
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========================================================================
-- vibecheck_analyses (legacy 72h cache, locked down)
-- =========================================================================

CREATE TABLE IF NOT EXISTS vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE vibecheck_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_analyses FORCE ROW LEVEL SECURITY;

-- TASK-1473.02 swaps the Cloud Run env from anon_key → service_role_key;
-- the public-grant policy is no longer needed. Drop it and revoke from anon
-- + authenticated so the only access path is the service role.
DROP POLICY IF EXISTS vibecheck_analyses_full_access ON vibecheck_analyses;
DROP POLICY IF EXISTS service_role_full_access ON vibecheck_analyses;
REVOKE ALL ON vibecheck_analyses FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_analyses_expires_at_idx ON vibecheck_analyses(expires_at);

-- =========================================================================
-- vibecheck_jobs (async pipeline lifecycle)
-- =========================================================================

CREATE TABLE IF NOT EXISTS vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_recommendation JSONB,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'partial', 'failed')),
    CONSTRAINT vibecheck_jobs_error_code_check
        CHECK (
            error_code IS NULL
            OR error_code IN (
                'invalid_url', 'unsafe_url', 'unsupported_site', 'upstream_error',
                'extraction_failed', 'section_failure', 'timeout',
                'rate_limited', 'internal'
            )
        ),
    CONSTRAINT vibecheck_jobs_terminal_finished_at
        CHECK (
            (status NOT IN ('done', 'partial', 'failed') AND finished_at IS NULL)
            OR (status IN ('done', 'partial', 'failed') AND finished_at IS NOT NULL)
        )
);

ALTER TABLE vibecheck_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_jobs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON vibecheck_jobs FROM anon, authenticated;

-- Dedup: hot path looks up by normalized_url to short-circuit duplicates.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_normalized_url_idx
    ON vibecheck_jobs(normalized_url);

-- Sweeper hot path: scan only non-terminal rows by status + age.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_status_created_at_idx
    ON vibecheck_jobs(status, created_at)
    WHERE status NOT IN ('done', 'partial', 'failed');

-- Heartbeat sweeper: stale heartbeats while in extracting/analyzing.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_heartbeat_idx
    ON vibecheck_jobs(heartbeat_at)
    WHERE status IN ('extracting', 'analyzing');

-- Purge sweeper: terminal jobs by finished_at.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_finished_at_idx
    ON vibecheck_jobs(finished_at)
    WHERE finished_at IS NOT NULL;

-- TASK-1473.46: cache-hit dedup invariant. The advisory lock in
-- `POST /api/analyze` serializes most concurrent submits, but two
-- contended submitters that lose the lock both fall into the contended
-- branch and can each call `_insert_cached_done_job` for the same
-- normalized_url, producing two duplicate cached done-job rows. The
-- vibecheck_analyses cache row stays single (source of truth) but the
-- job-row dedup invariant breaks for the cache-hit path. A partial
-- UNIQUE index lets the second insert ON CONFLICT DO NOTHING and the
-- caller re-fetch the surviving row.
CREATE UNIQUE INDEX IF NOT EXISTS
    vibecheck_jobs_unique_done_cached_normalized_url
    ON vibecheck_jobs(normalized_url)
    WHERE status = 'done' AND cached = true;

-- TASK-1473.35: e2e test hook for the section-retry Playwright spec.
-- When VIBECHECK_ALLOW_TEST_FAIL_HEADER=1 and the public POST carries
-- X-Vibecheck-Test-Fail-Slug: <slug>, the slug name is recorded here
-- and the orchestrator's `_run_section` forces a synthetic failure for
-- that slug. Always-null in production (the env flag defaults to off
-- so the route ignores the header).
ALTER TABLE vibecheck_jobs
    ADD COLUMN IF NOT EXISTS test_fail_slug TEXT;

-- TASK-1474.32: aggregate safety recommendation written after the four
-- safety slots complete. Nullable for old rows and optional-agent failure.
ALTER TABLE vibecheck_jobs
    ADD COLUMN IF NOT EXISTS safety_recommendation JSONB;

-- TASK-1474.23.02: post-Gemini stage breadcrumb. The orchestrator updates
-- `last_stage` synchronously at each stage boundary (persist_utterances,
-- set_analyzing, run_sections, safety_recommendation, finalize) so a
-- silent worker death between stages still leaves a DB-visible marker
-- pinpointing the dying stage. Always-NULL on legacy rows.
ALTER TABLE vibecheck_jobs
    ADD COLUMN IF NOT EXISTS last_stage TEXT;

-- TASK-1485.01: short preview blurb (~140 chars) populated at job-completion
-- time and surfaced by the "Recently vibe checked" gallery on vibecheck-web.
-- Computed deterministically from the assembled SidebarPayload so reads
-- are O(1) and cards never recompute on every poll. Nullable on legacy
-- rows; the gallery endpoint filters them out at the API boundary.
ALTER TABLE vibecheck_jobs
    ADD COLUMN IF NOT EXISTS preview_description TEXT;

-- =========================================================================
-- vibecheck_scrapes (persisted scrape bundles for retry resumption)
-- =========================================================================

CREATE TABLE IF NOT EXISTS vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    normalized_url TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '72 hours'),
    CONSTRAINT vibecheck_scrapes_page_kind_check
        CHECK (page_kind IN (
            'blog_post', 'forum_thread', 'hierarchical_thread',
            'blog_index', 'article', 'other'
        ))
);

ALTER TABLE vibecheck_scrapes ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_scrapes FORCE ROW LEVEL SECURITY;
REVOKE ALL ON vibecheck_scrapes FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_scrapes_expires_at_idx
    ON vibecheck_scrapes(expires_at);

-- =========================================================================
-- vibecheck_job_utterances (per-job utterance cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT vibecheck_job_utterances_kind_check
        CHECK (kind IN ('post', 'comment', 'reply'))
);

-- TASK-1473.36 (PR #407 BLOCKER): the GET /api/analyze/{job_id} poll
-- selector reads `u.page_title` / `u.page_kind` via correlated subqueries
-- to populate JobState (codex W4 P2-2). The columns lived only on
-- `vibecheck_scrapes` originally, so a fresh non-cached job's poll raised
-- asyncpg UndefinedColumn in production. Add as nullable text columns
-- with `page_kind` defaulting to the same `'other'` sentinel the scrape
-- bundle uses; existing rows backfill to `(NULL, 'other')` which the
-- selector's `IS NOT NULL` predicate already filters out.
ALTER TABLE vibecheck_job_utterances
    ADD COLUMN IF NOT EXISTS page_title TEXT;
ALTER TABLE vibecheck_job_utterances
    ADD COLUMN IF NOT EXISTS page_kind TEXT NOT NULL DEFAULT 'other';

-- TASK-1473.60: the NOT NULL DEFAULT 'other' from 1473.36 made every
-- backfilled row look "populated" to the IS NOT NULL poll selector.
-- Going forward, page_kind is only set when real extraction writes
-- utterances via persist_utterances (TASK-1473.57), so the column is
-- nullable and the default is dropped. Existing rows with
-- page_kind='other' (from the prior default) remain valid but are
-- distinguishable from NULL by the new selector.
ALTER TABLE vibecheck_job_utterances
    ALTER COLUMN page_kind DROP DEFAULT;
ALTER TABLE vibecheck_job_utterances
    ALTER COLUMN page_kind DROP NOT NULL;

ALTER TABLE vibecheck_job_utterances ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_job_utterances FORCE ROW LEVEL SECURITY;
REVOKE ALL ON vibecheck_job_utterances FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_job_utterances_job_id_idx
    ON vibecheck_job_utterances(job_id);

CREATE INDEX IF NOT EXISTS vibecheck_job_utterances_job_position_idx
    ON vibecheck_job_utterances(job_id, position);

-- =========================================================================
-- Sweeper functions (TASK-1473.04 AC4)
-- =========================================================================

-- Two-tier orphan detector:
--   * Pending tier — `pending` jobs older than 240s never got picked up by
--     a worker; mark them timed out.
--   * Heartbeat tier — `extracting`/`analyzing` jobs whose worker has not
--     touched `heartbeat_at` in 30s are stalled. We coalesce against
--     `updated_at` so a job that just transitioned out of `pending`
--     (and hasn't emitted its first heartbeat yet) gets a 30s grace period
--     instead of being failed instantly.
-- Marks them failed with error_code='timeout' so the frontend can render
-- the inline failure card with a retry option.
--
-- SECURITY DEFINER + OWNER postgres lets the cron-side caller mutate the
-- RLS-locked tables without holding broad role membership. EXECUTE is
-- revoked from PUBLIC/anon/authenticated below so only the postgres
-- superuser (and explicitly-granted roles) can invoke it. `search_path`
-- is pinned to defeat hijack via untrusted schemas.
CREATE OR REPLACE FUNCTION vibecheck_sweep_orphan_jobs()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    swept INT;
BEGIN
    UPDATE public.vibecheck_jobs
    SET
        status        = 'failed',
        error_code    = 'timeout',
        error_message = COALESCE(
            error_message,
            CASE
                WHEN status = 'pending' THEN 'job pending > 240s without dispatch'
                ELSE 'worker heartbeat stale > 30s'
            END
        ),
        updated_at    = now(),
        finished_at   = now()
    WHERE
        status NOT IN ('done', 'partial', 'failed')
        AND (
            -- Tier 1: pending jobs older than 240s never reached a worker.
            (status = 'pending' AND (now() - created_at) > INTERVAL '240 seconds')
            -- Tier 2: active jobs with stale heartbeat. COALESCE so a job
            -- that just became active gets at least one 30s heartbeat window.
            OR (
                status IN ('extracting', 'analyzing')
                AND (now() - COALESCE(heartbeat_at, updated_at, created_at))
                    > INTERVAL '30 seconds'
            )
        );
    GET DIAGNOSTICS swept = ROW_COUNT;
    RETURN swept;
END;
$$;
ALTER FUNCTION vibecheck_sweep_orphan_jobs() OWNER TO postgres;
REVOKE ALL ON FUNCTION vibecheck_sweep_orphan_jobs() FROM PUBLIC, anon, authenticated;

-- Purges terminal jobs older than 7 days. Cascades to job_utterances via FK.
-- Scrape bundles are TTL-pruned independently via vibecheck_scrapes.expires_at
-- (used by future tickets); kept here as a single hourly maintenance pass.
-- See vibecheck_sweep_orphan_jobs for the SECURITY DEFINER rationale.
CREATE OR REPLACE FUNCTION vibecheck_purge_terminal_jobs()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    purged INT;
BEGIN
    DELETE FROM public.vibecheck_jobs
    WHERE status IN ('done', 'partial', 'failed')
      AND finished_at IS NOT NULL
      AND finished_at < (now() - INTERVAL '7 days');
    GET DIAGNOSTICS purged = ROW_COUNT;

    DELETE FROM public.vibecheck_scrapes
    WHERE expires_at < now();

    DELETE FROM public.vibecheck_analyses
    WHERE expires_at < now();

    DELETE FROM public.vibecheck_web_risk_lookups WHERE expires_at < now();

    RETURN purged;
END;
$$;
ALTER FUNCTION vibecheck_purge_terminal_jobs() OWNER TO postgres;
REVOKE ALL ON FUNCTION vibecheck_purge_terminal_jobs() FROM PUBLIC, anon, authenticated;

-- =========================================================================
-- vibecheck_web_risk_lookups (TASK-1474.03 — Google Web Risk cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS vibecheck_web_risk_lookups (
    url TEXT PRIMARY KEY,
    finding_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx
    ON vibecheck_web_risk_lookups (expires_at);
ALTER TABLE vibecheck_web_risk_lookups ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_web_risk_lookups FORCE ROW LEVEL SECURITY;
REVOKE ALL ON vibecheck_web_risk_lookups FROM anon, authenticated;

-- =========================================================================
-- Extend vibecheck_jobs_error_code_check to include 'unsafe_url'
-- (TASK-1474.03)
-- =========================================================================
-- Use ALTER ... DROP CONSTRAINT IF EXISTS + ADD inline instead of a DO-block
-- information_schema probe: the probe has a TOCTOU window where a concurrent
-- schema apply can drop the constraint between the EXISTS check and the
-- subsequent DROP, producing a "constraint does not exist" error (codex P2.5).
-- DROP ... IF EXISTS collapses both steps into one atomic, idempotent call.
ALTER TABLE vibecheck_jobs
  DROP CONSTRAINT IF EXISTS vibecheck_jobs_error_code_check;

ALTER TABLE vibecheck_jobs
  ADD CONSTRAINT vibecheck_jobs_error_code_check
  CHECK (
    error_code IS NULL
    OR error_code IN (
      'invalid_url', 'unsupported_site', 'upstream_error',
      'extraction_failed', 'timeout', 'rate_limited', 'internal',
      'unsafe_url', 'section_failure'
    )
  );

-- =========================================================================
-- pg_cron schedules (idempotent)
-- =========================================================================
-- cron.schedule fails on duplicate jobname, so unschedule first when present.
-- Wrap in DO block so a missing cron schema (extension not yet enabled) is a
-- single recoverable error rather than a parser failure.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'vibecheck-orphan-sweep') THEN
        PERFORM cron.unschedule('vibecheck-orphan-sweep');
    END IF;
    PERFORM cron.schedule(
        'vibecheck-orphan-sweep',
        '* * * * *',
        $cron$SELECT public.vibecheck_sweep_orphan_jobs();$cron$
    );

    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'vibecheck-purge-terminal') THEN
        PERFORM cron.unschedule('vibecheck-purge-terminal');
    END IF;
    PERFORM cron.schedule(
        'vibecheck-purge-terminal',
        '5 * * * *',
        $cron$SELECT public.vibecheck_purge_terminal_jobs();$cron$
    );
END
$$;
