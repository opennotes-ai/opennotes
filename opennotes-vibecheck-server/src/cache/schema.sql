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
-- TEMPORARY exec_sql bootstrap (TASK-1490)
-- =========================================================================
-- This function is the stop-gap that lets vibecheck-server self-heal this
-- schema at startup through Supabase PostgREST RPC. Remove it only after the
-- opennotes-server merge lands and Alembic owns vibecheck schema changes.
-- Threat model: any service-role key holder can invoke arbitrary SQL through
-- this SECURITY DEFINER function; keeping it is a privilege-escalation risk.
-- Removal is tracked by TASK-1490.20.
-- Operators must seed the same block once via docs/exec-sql-bootstrap.md §1
-- (in this repo) before the first deploy to an environment where exec_sql is absent.
--
-- Ownership decision (TASK-1490.21): exec_sql remains postgres-owned (the
-- default ownership of CREATE FUNCTION by the seeding role) for the duration
-- of this bootstrap window. Re-applying schema.sql as service_role via
-- exec_sql re-issues ALTER TABLE ENABLE RLS, ALTER FUNCTION OWNER TO postgres,
-- REVOKE, and cron.schedule calls — all of which require object-owner / pg_cron
-- powers that a constrained role (vibecheck_schema_admin) cannot hold on
-- postgres-owned objects. The security boundary is the EXECUTE grant: only
-- service_role can call exec_sql, and service_role already bypasses RLS on
-- the same Supabase project. A separate non-superuser owner does not raise
-- the security floor here.
-- search_path decision (TASK-1490.10, TASK-1490.21, TASK-1490.39):
-- exec_sql is locked to `pg_catalog, pg_temp`; all DDL targets and built-in
-- calls below are schema-qualified so the apply path is not dependent on
-- public search_path resolution or Supabase extension placement. Do NOT flip
-- search_path; if a function call fails to resolve, qualify the call instead.
SET LOCAL lock_timeout = '30s';
SELECT pg_catalog.pg_advisory_xact_lock(1490, pg_catalog.hashtext('schema_apply')::int);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'vibecheck_schema_admin') THEN
        CREATE ROLE vibecheck_schema_admin;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT pg_catalog.has_schema_privilege('vibecheck_schema_admin', 'public', 'CREATE') THEN
        GRANT USAGE, CREATE ON SCHEMA public TO vibecheck_schema_admin;
    END IF;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'vibecheck_schema_admin already exists but current role cannot grant public schema privileges';
END
$$;

CREATE OR REPLACE FUNCTION public.exec_sql(sql text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE LOG 'vibecheck exec_sql apply length=% hash=%',
        pg_catalog.length(sql),
        pg_catalog.md5(sql);
    EXECUTE sql;
END;
$$;
COMMENT ON FUNCTION public.exec_sql(text) IS
    'TEMPORARY TASK-1490.20: service-role-only schema bootstrap; postgres-owned so re-apply via exec_sql can ALTER TABLE/FUNCTION owned by postgres without InsufficientPrivilege. Do NOT flip search_path: TASK-1490.10/TASK-1490.21/TASK-1490.39 lock it to pg_catalog, pg_temp; qualify DDL or function calls instead. Remove once Alembic owns vibecheck changes (TASK-1490.20).';
REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;

-- =========================================================================
-- Extensions
-- =========================================================================

-- pg_cron must be allowlisted in the Supabase dashboard before this runs
-- (TASK-1473.02 §10.1). The `IF NOT EXISTS` keeps the file re-runnable
-- when the extension is already present.
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;

-- =========================================================================
-- vibecheck_analyses (legacy 72h cache, locked down)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE public.vibecheck_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_analyses FORCE ROW LEVEL SECURITY;

-- TASK-1473.02 swaps the Cloud Run env from anon_key → service_role_key;
-- the public-grant policy is no longer needed. Drop it and revoke from anon
-- + authenticated so the only access path is the service role.
DROP POLICY IF EXISTS vibecheck_analyses_full_access ON public.vibecheck_analyses;
DROP POLICY IF EXISTS service_role_full_access ON public.vibecheck_analyses;
REVOKE ALL ON public.vibecheck_analyses FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_analyses_expires_at_idx ON public.vibecheck_analyses(expires_at);

-- =========================================================================
-- vibecheck_jobs (async pipeline lifecycle)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_jobs (
    job_id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    url TEXT NOT NULL,
    normalized_url TEXT NOT NULL,
    host TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_id UUID NOT NULL DEFAULT extensions.uuid_generate_v4(),
    error_code TEXT,
    error_message TEXT,
    error_host TEXT,
    sections JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_recommendation JSONB,
    sidebar_payload JSONB,
    cached BOOLEAN NOT NULL DEFAULT false,
    source_type TEXT NOT NULL DEFAULT 'url',
    extract_transient_attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    heartbeat_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CONSTRAINT vibecheck_jobs_status_check
        CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'partial', 'failed')),
    CONSTRAINT vibecheck_jobs_error_code_check
        CHECK (
            error_code IS NULL
            OR error_code IN (
                'invalid_url', 'unsafe_url', 'unsupported_site', 'upstream_error',
                'extraction_failed', 'section_failure', 'timeout', 'pdf_too_large',
                'pdf_extraction_failed',
                'rate_limited', 'internal'
            )
        ),
    CONSTRAINT vibecheck_jobs_source_type_check
        CHECK (source_type IN ('url', 'pdf', 'browser_html')),
    CONSTRAINT vibecheck_jobs_terminal_finished_at
        CHECK (
            (status NOT IN ('done', 'partial', 'failed') AND finished_at IS NULL)
            OR (status IN ('done', 'partial', 'failed') AND finished_at IS NOT NULL)
        )
);

ALTER TABLE public.vibecheck_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_jobs FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_jobs FROM anon, authenticated;

-- Dedup: hot path looks up by normalized_url to short-circuit duplicates.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_normalized_url_idx
    ON public.vibecheck_jobs(normalized_url);

-- Sweeper hot path: scan only non-terminal rows by status + age.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_status_created_at_idx
    ON public.vibecheck_jobs(status, created_at)
    WHERE status NOT IN ('done', 'partial', 'failed');

-- Heartbeat sweeper: stale heartbeats while in extracting/analyzing.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_heartbeat_idx
    ON public.vibecheck_jobs(heartbeat_at)
    WHERE status IN ('extracting', 'analyzing');

-- Purge sweeper: terminal jobs by finished_at.
CREATE INDEX IF NOT EXISTS vibecheck_jobs_finished_at_idx
    ON public.vibecheck_jobs(finished_at)
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
    ON public.vibecheck_jobs(normalized_url)
    WHERE status = 'done' AND cached = true;

-- TASK-1473.35: e2e test hook for the section-retry Playwright spec.
-- When VIBECHECK_ALLOW_TEST_FAIL_HEADER=1 and the public POST carries
-- X-Vibecheck-Test-Fail-Slug: <slug>, the slug name is recorded here
-- and the orchestrator's `_run_section` forces a synthetic failure for
-- that slug. Always-null in production (the env flag defaults to off
-- so the route ignores the header).
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS test_fail_slug TEXT;

-- TASK-1474.32: aggregate safety recommendation written after the four
-- safety slots complete. Nullable for old rows and optional-agent failure.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS safety_recommendation JSONB;

-- TASK-1508.04.01: synthesized headline summation (1-2 sentence opening
-- line) rendered above the safety recommendation. Nullable for old rows
-- and optional-agent failure; finalize falls back to None when missing.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS headline_summary JSONB;

-- TASK-1508.19.04: persisted weather report for weather-augmented
-- analyses. Nullable JSONB for backward compatibility on pre-existing rows.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS weather_report JSONB;

-- TASK-1578.02: rewrite retired TruthLabel values in persisted weather
-- report JSON before the stricter Pydantic enum reads it back. This preserves
-- the distinction between sourced factual claims and unsourced factual claims.
UPDATE public.vibecheck_jobs
SET weather_report = jsonb_set(
    weather_report,
    '{truth,label}',
    CASE
        WHEN weather_report->'truth'->>'label' = 'mostly_factual'
            THEN '"factual_claims"'::jsonb
        WHEN weather_report->'truth'->>'label' = 'self_reported'
            THEN '"first_person"'::jsonb
        ELSE weather_report->'truth'->'label'
    END,
    false
)
WHERE weather_report->'truth'->>'label'
    IN ('mostly_factual', 'self_reported');

UPDATE public.vibecheck_jobs vj
SET weather_report = jsonb_set(
    vj.weather_report,
    '{truth,alternatives}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN alt.value->>'label' = 'mostly_factual'
                    THEN jsonb_set(alt.value, '{label}', '"factual_claims"'::jsonb, false)
                WHEN alt.value->>'label' = 'self_reported'
                    THEN jsonb_set(alt.value, '{label}', '"first_person"'::jsonb, false)
                ELSE alt.value
            END
            ORDER BY alt.ordinality
        )
        FROM jsonb_array_elements(
            vj.weather_report->'truth'->'alternatives'
        ) WITH ORDINALITY AS alt(value, ordinality)
    ),
    false
)
WHERE jsonb_typeof(vj.weather_report->'truth'->'alternatives') = 'array'
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(
          vj.weather_report->'truth'->'alternatives'
      ) alt
      WHERE alt->>'label' IN ('mostly_factual', 'self_reported')
  );

UPDATE public.vibecheck_jobs
SET sidebar_payload = jsonb_set(
    sidebar_payload,
    '{weather_report,truth,label}',
    CASE
        WHEN sidebar_payload->'weather_report'->'truth'->>'label' = 'mostly_factual'
            THEN '"factual_claims"'::jsonb
        WHEN sidebar_payload->'weather_report'->'truth'->>'label' = 'self_reported'
            THEN '"first_person"'::jsonb
        ELSE sidebar_payload->'weather_report'->'truth'->'label'
    END,
    false
)
WHERE sidebar_payload->'weather_report'->'truth'->>'label'
    IN ('mostly_factual', 'self_reported');

UPDATE public.vibecheck_jobs vj
SET sidebar_payload = jsonb_set(
    vj.sidebar_payload,
    '{weather_report,truth,alternatives}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN alt.value->>'label' = 'mostly_factual'
                    THEN jsonb_set(alt.value, '{label}', '"factual_claims"'::jsonb, false)
                WHEN alt.value->>'label' = 'self_reported'
                    THEN jsonb_set(alt.value, '{label}', '"first_person"'::jsonb, false)
                ELSE alt.value
            END
            ORDER BY alt.ordinality
        )
        FROM jsonb_array_elements(
            vj.sidebar_payload->'weather_report'->'truth'->'alternatives'
        ) WITH ORDINALITY AS alt(value, ordinality)
    ),
    false
)
WHERE jsonb_typeof(vj.sidebar_payload->'weather_report'->'truth'->'alternatives') = 'array'
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(
          vj.sidebar_payload->'weather_report'->'truth'->'alternatives'
      ) alt
      WHERE alt->>'label' IN ('mostly_factual', 'self_reported')
  );

-- TASK-1474.23.02: post-Gemini stage breadcrumb. The orchestrator updates
-- `last_stage` synchronously at each stage boundary (persist_utterances,
-- set_analyzing, run_sections, safety_recommendation, finalize) so a
-- silent worker death between stages still leaves a DB-visible marker
-- pinpointing the dying stage. Always-NULL on legacy rows.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS last_stage TEXT;

-- TASK-1485.01: short preview blurb (~140 chars) populated at job-completion
-- time and surfaced by the "Recently vibe checked" gallery on vibecheck-web.
-- Computed deterministically from the assembled SidebarPayload so reads
-- are O(1) and cards never recompute on every poll. Nullable on legacy
-- rows; the gallery endpoint filters them out at the API boundary.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS preview_description TEXT;

-- TASK-1521: browser-sourced HTML jobs are excluded from the public
-- recent-gallery path and get a trusted scrape-cache tier.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'url';

ALTER TABLE public.vibecheck_jobs
    DROP CONSTRAINT IF EXISTS vibecheck_jobs_source_type_check;
ALTER TABLE public.vibecheck_jobs
    ADD CONSTRAINT vibecheck_jobs_source_type_check
    CHECK (source_type IN ('url', 'pdf', 'browser_html'));

-- TASK-1474.23.03: in-row backstop counter for the extract-stage retry path.
-- The orchestrator increments this column each time the utterance-extract
-- arm raises a TransientExtractionError so Cloud Tasks can redeliver. Once
-- the counter exceeds the configured cap, the orchestrator translates the
-- next transient failure into a TerminalError(UPSTREAM_ERROR) so the job
-- terminates instead of silently exhausting Cloud Tasks max_attempts. NOT
-- NULL DEFAULT 0 covers legacy rows during the first deploy; the column is
-- additive-only — no readers/writers in this subtask, those land in
-- TASK-1474.23.03.04 + .05.
ALTER TABLE public.vibecheck_jobs
    ADD COLUMN IF NOT EXISTS extract_transient_attempts INT NOT NULL DEFAULT 0;

-- =========================================================================
-- vibecheck_pdf_archives (PDF raw HTML TTL cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_pdf_archives (
    job_id UUID PRIMARY KEY REFERENCES public.vibecheck_jobs(job_id) ON DELETE CASCADE,
    html TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (pg_catalog.now() + INTERVAL '7 days')
);

ALTER TABLE public.vibecheck_pdf_archives ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_pdf_archives FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_pdf_archives FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_pdf_archives_expires_at_idx
    ON public.vibecheck_pdf_archives (expires_at);

-- =========================================================================
-- vibecheck_scrapes (persisted scrape bundles for retry resumption)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_scrapes (
    scrape_id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    normalized_url TEXT NOT NULL,
    job_id UUID,
    attempt_id UUID,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    page_kind TEXT NOT NULL DEFAULT 'other',
    page_title TEXT,
    markdown TEXT,
    html TEXT,
    screenshot_storage_key TEXT,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (pg_catalog.now() + INTERVAL '72 hours'),
    CONSTRAINT vibecheck_scrapes_page_kind_check
        CHECK (page_kind IN (
            'blog_post', 'forum_thread', 'hierarchical_thread',
            'blog_index', 'article', 'other'
        ))
);

ALTER TABLE public.vibecheck_scrapes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_scrapes FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_scrapes FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_scrapes_expires_at_idx
    ON public.vibecheck_scrapes(expires_at);

-- TASK-1488.01: tier separates Tier 1 (`scrape`, cheap Firecrawl /scrape)
-- from Tier 2 (`interact`, post-fallback Firecrawl /interact). Both rows
-- coexist for the same normalized_url so a Tier 1 failure cache entry
-- can't short-circuit a retry that escalated successfully to Tier 2.
-- Existing rows backfill to 'scrape' via the DEFAULT.
ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'scrape';

ALTER TABLE public.vibecheck_scrapes
    DROP CONSTRAINT IF EXISTS vibecheck_scrapes_tier_check;
ALTER TABLE public.vibecheck_scrapes
    ADD CONSTRAINT vibecheck_scrapes_tier_check
    CHECK (tier IN ('scrape', 'interact', 'browser_html'));

-- Replace UNIQUE(normalized_url) with composite UNIQUE(normalized_url, tier).
-- Postgres named the original UNIQUE either via the inline column constraint
-- (`vibecheck_scrapes_normalized_url_key`) or via an explicit CONSTRAINT
-- name in older revisions; drop both shapes guarded by IF EXISTS so re-runs
-- of this file leave a clean slate. Only shared cache tiers keep the
-- `(normalized_url, tier)` uniqueness contract; browser_html rows are
-- job-scoped so repeated same-URL submissions cannot overwrite each other.
ALTER TABLE public.vibecheck_scrapes
    DROP CONSTRAINT IF EXISTS vibecheck_scrapes_normalized_url_key;
ALTER TABLE public.vibecheck_scrapes
    DROP CONSTRAINT IF EXISTS vibecheck_scrapes_normalized_url_unique;
DROP INDEX IF EXISTS public.vibecheck_scrapes_normalized_url_key;
DROP INDEX IF EXISTS public.vibecheck_scrapes_normalized_url_tier_idx;

ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS job_id UUID;
ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS attempt_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS
    vibecheck_scrapes_normalized_url_tier_idx
    ON public.vibecheck_scrapes (normalized_url, tier)
    WHERE tier IN ('scrape', 'interact');

CREATE UNIQUE INDEX IF NOT EXISTS
    vibecheck_scrapes_browser_html_job_attempt_idx
    ON public.vibecheck_scrapes (job_id, attempt_id)
    WHERE tier = 'browser_html';

-- TASK-1488.18: persist Firecrawl's resolved post-redirect URL
-- (`metadata.source_url`) so cache reads rehydrate `metadata.source_url`
-- from the actual resolved host, not the input URL. Without this,
-- `_revalidate_final_url` on a poisoned cache replay sees the input URL
-- as both the lookup key and the resolved URL — the SSRF re-check is
-- silently bypassed. Nullable + no default so legacy rows hydrate via
-- the row's `url` fallback in `_row_to_cached_scrape`.
ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS final_url TEXT;

-- TASK-1488.18: tombstone marker so `evict()` can fence concurrent
-- `put()` calls that started before the evict but commit after. On
-- evict, the row is deleted and a tombstone row is upserted with
-- `evicted_at = now()` and `expires_at` in the past. `put()` checks
-- this column before its own upsert and aborts when a recent eviction
-- is observed. Tombstones are filtered out of `get()` by the existing
-- `expires_at > now()` predicate so callers never see them.
ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS evicted_at TIMESTAMPTZ;

-- TASK-1577.01: persist Firecrawl rawHtml alongside the main-content html
-- so future consumers can reach the original SSR document for re-extraction
-- or debugging without paying for another scrape. The main-content `html`
-- column is what archive_preview already serves; `raw_html` is forward-
-- looking storage with no current reader. Nullable + no default so legacy
-- rows pre-migration carry NULL until the next put() refreshes them.
ALTER TABLE public.vibecheck_scrapes
    ADD COLUMN IF NOT EXISTS raw_html TEXT;

-- TASK-1488.18.01: atomically persist a scrape row unless an evict
-- tombstone landed after the caller's write-fence anchor. The predicate
-- lives inside `ON CONFLICT DO UPDATE`, so an evict that arrives between
-- the application preflight read and the final write cannot be overwritten.
--
-- TASK-1577.01: a 15-arg signature with `p_raw_html` is added below.
-- The prior 14-arg form is preserved as a shim that delegates with
-- `p_raw_html => NULL` so that during a rolling Cloud Run deploy the
-- old replicas (still calling the 14-arg form) keep working until they
-- drain. Both forms must coexist; do NOT drop the 14-arg form.
CREATE OR REPLACE FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    p_normalized_url TEXT,
    p_tier TEXT,
    p_url TEXT,
    p_final_url TEXT,
    p_host TEXT,
    p_page_kind TEXT,
    p_page_title TEXT,
    p_markdown TEXT,
    p_html TEXT,
    p_raw_html TEXT,
    p_screenshot_storage_key TEXT,
    p_scraped_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ,
    p_put_started_at TIMESTAMPTZ,
    p_clock_skew_seconds INT  -- TASK-1577.01: no DEFAULT so the 14-arg shim
                              -- below is unambiguous for positional callers.
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    wrote_row BOOLEAN;
BEGIN
    INSERT INTO public.vibecheck_scrapes (
        normalized_url, tier, url, final_url, host, page_kind, page_title,
        markdown, html, raw_html, screenshot_storage_key, scraped_at,
        expires_at, evicted_at
    )
    VALUES (
        p_normalized_url, p_tier, p_url, p_final_url, p_host, p_page_kind,
        p_page_title, p_markdown, p_html, p_raw_html, p_screenshot_storage_key,
        p_scraped_at, p_expires_at, NULL
    )
    ON CONFLICT (normalized_url, tier)
    WHERE tier IN ('scrape', 'interact')
    DO UPDATE
    SET url = EXCLUDED.url,
        final_url = EXCLUDED.final_url,
        host = EXCLUDED.host,
        page_kind = EXCLUDED.page_kind,
        page_title = EXCLUDED.page_title,
        markdown = EXCLUDED.markdown,
        html = EXCLUDED.html,
        raw_html = EXCLUDED.raw_html,
        screenshot_storage_key = EXCLUDED.screenshot_storage_key,
        scraped_at = EXCLUDED.scraped_at,
        expires_at = EXCLUDED.expires_at,
        evicted_at = EXCLUDED.evicted_at
    WHERE public.vibecheck_scrapes.evicted_at IS NULL
       OR public.vibecheck_scrapes.evicted_at < (
           p_put_started_at
           - pg_catalog.make_interval(secs => p_clock_skew_seconds::double precision)
       )
    RETURNING TRUE INTO wrote_row;

    RETURN COALESCE(wrote_row, FALSE);
END;
$$;
ALTER FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ, INT
) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ, INT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
    TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ, INT
) TO service_role;

-- TASK-1577.01 rolling-deploy shim: old replicas (pre-1577.01 image)
-- continue calling the 14-arg signature until they drain. Routes to the
-- 15-arg form with raw_html defaulted to NULL so old + new can serve
-- traffic concurrently without PostgREST function-resolution failures.
-- Drop this shim only after the 14-arg image is fully retired (tracked
-- separately so the cleanup is intentional, not coincidental).
CREATE OR REPLACE FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    p_normalized_url TEXT,
    p_tier TEXT,
    p_url TEXT,
    p_final_url TEXT,
    p_host TEXT,
    p_page_kind TEXT,
    p_page_title TEXT,
    p_markdown TEXT,
    p_html TEXT,
    p_screenshot_storage_key TEXT,
    p_scraped_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ,
    p_put_started_at TIMESTAMPTZ,
    p_clock_skew_seconds INT DEFAULT 1  -- TASK-1583.01: preserve the
                                        -- legacy default so schema reapply
                                        -- can replace pre-1577.01 functions.
)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT public.vibecheck_upsert_scrape_if_not_evicted(
        p_normalized_url,
        p_tier,
        p_url,
        p_final_url,
        p_host,
        p_page_kind,
        p_page_title,
        p_markdown,
        p_html,
        NULL::TEXT,
        p_screenshot_storage_key,
        p_scraped_at,
        p_expires_at,
        p_put_started_at,
        p_clock_skew_seconds
    );
$$;
ALTER FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ,
    TIMESTAMPTZ, TIMESTAMPTZ, INT
) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ,
    TIMESTAMPTZ, TIMESTAMPTZ, INT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.vibecheck_upsert_scrape_if_not_evicted(
    TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ,
    TIMESTAMPTZ, TIMESTAMPTZ, INT
) TO service_role;

CREATE OR REPLACE FUNCTION public.vibecheck_upsert_scrape_evict_tombstone(
    p_normalized_url TEXT,
    p_tier TEXT,
    p_url TEXT,
    p_host TEXT,
    p_scraped_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ,
    p_evicted_at TIMESTAMPTZ
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    INSERT INTO public.vibecheck_scrapes (
        normalized_url, tier, url, final_url, host, page_kind, page_title,
        markdown, html, raw_html, screenshot_storage_key, scraped_at,
        expires_at, evicted_at
    )
    VALUES (
        p_normalized_url, p_tier, p_url, NULL, p_host, 'other', NULL,
        NULL, NULL, NULL, NULL, p_scraped_at, p_expires_at, p_evicted_at
    )
    ON CONFLICT (normalized_url, tier)
    WHERE tier IN ('scrape', 'interact')
    DO UPDATE
    SET url = EXCLUDED.url,
        final_url = EXCLUDED.final_url,
        host = EXCLUDED.host,
        page_kind = EXCLUDED.page_kind,
        page_title = EXCLUDED.page_title,
        markdown = EXCLUDED.markdown,
        html = EXCLUDED.html,
        raw_html = EXCLUDED.raw_html,
        screenshot_storage_key = EXCLUDED.screenshot_storage_key,
        scraped_at = EXCLUDED.scraped_at,
        expires_at = EXCLUDED.expires_at,
        evicted_at = EXCLUDED.evicted_at;
END;
$$;
ALTER FUNCTION public.vibecheck_upsert_scrape_evict_tombstone(
    TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ
) OWNER TO postgres;
REVOKE ALL ON FUNCTION public.vibecheck_upsert_scrape_evict_tombstone(
    TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.vibecheck_upsert_scrape_evict_tombstone(
    TEXT, TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TIMESTAMPTZ
) TO service_role;

-- PostgREST caches RPC signatures. When startup applies this schema through
-- `public.exec_sql`, the new atomic scrape-upsert RPC must be visible before
-- request traffic calls it.
NOTIFY pgrst, 'reload schema';

-- =========================================================================
-- vibecheck_job_utterances (per-job utterance cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_job_utterances (
    utterance_pk UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES public.vibecheck_jobs(job_id) ON DELETE CASCADE,
    utterance_id TEXT,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    timestamp_at TIMESTAMPTZ,
    parent_id TEXT,
    position INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
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
ALTER TABLE public.vibecheck_job_utterances
    ADD COLUMN IF NOT EXISTS page_title TEXT;
ALTER TABLE public.vibecheck_job_utterances
    ADD COLUMN IF NOT EXISTS page_kind TEXT NOT NULL DEFAULT 'other';
ALTER TABLE public.vibecheck_job_utterances
    ADD COLUMN IF NOT EXISTS utterance_stream_type TEXT NOT NULL DEFAULT 'unknown';

-- TASK-1473.60: the NOT NULL DEFAULT 'other' from 1473.36 made every
-- backfilled row look "populated" to the IS NOT NULL poll selector.
-- Going forward, page_kind is only set when real extraction writes
-- utterances via persist_utterances (TASK-1473.57), so the column is
-- nullable and the default is dropped. Existing rows with
-- page_kind='other' (from the prior default) remain valid but are
-- distinguishable from NULL by the new selector.
ALTER TABLE public.vibecheck_job_utterances
    ALTER COLUMN page_kind DROP DEFAULT;
ALTER TABLE public.vibecheck_job_utterances
    ALTER COLUMN page_kind DROP NOT NULL;
ALTER TABLE public.vibecheck_job_utterances
    ALTER COLUMN utterance_stream_type DROP DEFAULT;
ALTER TABLE public.vibecheck_job_utterances
    ALTER COLUMN utterance_stream_type DROP NOT NULL;

ALTER TABLE public.vibecheck_job_utterances ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_job_utterances FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_job_utterances FROM anon, authenticated;

CREATE INDEX IF NOT EXISTS vibecheck_job_utterances_job_id_idx
    ON public.vibecheck_job_utterances(job_id);

CREATE INDEX IF NOT EXISTS vibecheck_job_utterances_job_position_idx
    ON public.vibecheck_job_utterances(job_id, position);

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
CREATE OR REPLACE FUNCTION public.vibecheck_sweep_orphan_jobs()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
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
        updated_at    = pg_catalog.now(),
        finished_at   = pg_catalog.now()
    WHERE
        status NOT IN ('done', 'partial', 'failed')
        AND (
            -- Tier 1: pending jobs older than 240s never reached a worker.
            (status = 'pending' AND (pg_catalog.now() - created_at) > INTERVAL '240 seconds')
            -- Tier 2: active jobs with stale heartbeat. COALESCE so a job
            -- that just became active gets at least one 30s heartbeat window.
            OR (
                status IN ('extracting', 'analyzing')
                AND (pg_catalog.now() - COALESCE(heartbeat_at, updated_at, created_at))
                    > INTERVAL '30 seconds'
            )
        );
    GET DIAGNOSTICS swept = ROW_COUNT;
    RETURN swept;
END;
$$;
ALTER FUNCTION public.vibecheck_sweep_orphan_jobs() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.vibecheck_sweep_orphan_jobs() FROM PUBLIC, anon, authenticated;

-- Purges terminal jobs older than 7 days. Cascades to job_utterances via FK.
-- Scrape bundles are TTL-pruned independently via vibecheck_scrapes.expires_at
-- (used by future tickets); kept here as a single hourly maintenance pass.
-- See vibecheck_sweep_orphan_jobs for the SECURITY DEFINER rationale.
-- expired_at: soft-delete marker set by vibecheck_purge_terminal_jobs (TASK-1541).
-- Terminal jobs older than 7 days have their sensitive payload columns nulled
-- and `expired_at = now()` set so the row sticks around (preserving job_id +
-- url + status for audit/idempotency) without retaining user-content payloads.
ALTER TABLE public.vibecheck_jobs
  ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS vibecheck_jobs_expired_at_idx
  ON public.vibecheck_jobs (expired_at)
  WHERE expired_at IS NOT NULL;

-- protected: operator-controlled flag that exempts a job from TTL reaping
-- (TASK-1540). No API surface — operators flip this in the Supabase table
-- editor. When true, the job and its `vibecheck_analyses` cache row are
-- never soft-deleted by `vibecheck_purge_terminal_jobs()`.
--
-- Other caches (vibecheck_scrapes, vibecheck_web_risk_lookups) are
-- explicitly NOT propagated — they are regeneration caches keyed by URL
-- and do not need protection: the next read will simply re-populate them.
-- vibecheck_pdf_archives IS protected (see vibecheck_purge_terminal_jobs)
-- because it stores user-uploaded PDF HTML that cannot be re-fetched from
-- a URL — losing it would permanently break the `pdf_archive_url`
-- reference on the protected job.
ALTER TABLE public.vibecheck_jobs
  ADD COLUMN IF NOT EXISTS protected BOOLEAN NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.vibecheck_purge_terminal_jobs()
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    purged INT;
BEGIN
    WITH expired AS (
        UPDATE public.vibecheck_jobs
        SET
            expired_at            = pg_catalog.now(),
            sidebar_payload       = NULL,
            sections              = '{}'::jsonb,
            error_message         = NULL,
            headline_summary      = NULL,
            safety_recommendation = NULL,
            last_stage            = NULL
        WHERE status IN ('done', 'partial', 'failed')
          AND finished_at IS NOT NULL
          AND finished_at < (pg_catalog.now() - INTERVAL '7 days')
          AND expired_at IS NULL
          AND protected = false  -- TASK-1540: skip operator-flagged jobs
        RETURNING job_id
    ),
    del_utterances AS (
        DELETE FROM public.vibecheck_job_utterances
        WHERE job_id IN (SELECT job_id FROM expired)
        RETURNING 1
    )
    SELECT COUNT(*) INTO purged FROM expired;

    -- vibecheck_scrapes and vibecheck_web_risk_lookups intentionally do NOT
    -- honor the protected flag — they are regeneration caches keyed by
    -- URL/host that a future read trivially re-populates (TASK-1540).
    -- vibecheck_analyses and vibecheck_pdf_archives DO honor the protected
    -- flag because they carry user-visible state (sidebar payload) or
    -- user-uploaded content (PDF HTML) that cannot be regenerated from a URL.
    DELETE FROM public.vibecheck_scrapes
    WHERE expires_at < pg_catalog.now();

    -- TASK-1540: protect the pdf_archives row for any protected job, otherwise
    -- the user-uploaded PDF HTML (which cannot be re-fetched) would vanish 7
    -- days after upload while the (protected) job row continued to exist,
    -- permanently breaking the `pdf_archive_url` reference.
    DELETE FROM public.vibecheck_pdf_archives
    WHERE expires_at < pg_catalog.now()
      AND NOT EXISTS (
          SELECT 1 FROM public.vibecheck_jobs j
          WHERE j.job_id = public.vibecheck_pdf_archives.job_id
            AND j.protected = true
      );

    -- TASK-1540: protect the analyses cache row for any protected job that
    -- shares the same normalized_url, otherwise the sidebar payload would
    -- vanish from the cache 72h after the job ran while the (protected)
    -- job row continued to exist.
    DELETE FROM public.vibecheck_analyses
    WHERE expires_at < pg_catalog.now()
      AND NOT EXISTS (
          SELECT 1 FROM public.vibecheck_jobs j
          WHERE j.normalized_url = public.vibecheck_analyses.url
            AND j.protected = true
      );

    DELETE FROM public.vibecheck_web_risk_lookups WHERE expires_at < pg_catalog.now();
    -- TASK-1483.24: per-URL Vision API caches expire on TTL; reap stale rows
    -- so the high-cardinality URL keys do not grow unbounded.
    DELETE FROM public.vibecheck_image_analysis_cache WHERE expires_at < pg_catalog.now();
    DELETE FROM public.vibecheck_video_analysis_cache WHERE expires_at < pg_catalog.now();

    RETURN purged;
END;
$$;
ALTER FUNCTION public.vibecheck_purge_terminal_jobs() OWNER TO postgres;
REVOKE ALL ON FUNCTION public.vibecheck_purge_terminal_jobs() FROM PUBLIC, anon, authenticated;

-- =========================================================================
-- vibecheck_web_risk_lookups (TASK-1474.03 — Google Web Risk cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_web_risk_lookups (
    url TEXT PRIMARY KEY,
    finding_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_web_risk_lookups_expires_at_idx
    ON public.vibecheck_web_risk_lookups (expires_at);
ALTER TABLE public.vibecheck_web_risk_lookups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_web_risk_lookups FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_web_risk_lookups FROM anon, authenticated;

-- =========================================================================
-- vibecheck_image_analysis_cache (TASK-1483.24 — Vision API SafeSearch cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_image_analysis_cache (
    image_url TEXT PRIMARY KEY,
    result_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_image_analysis_cache_expires_at_idx
    ON public.vibecheck_image_analysis_cache (expires_at);
ALTER TABLE public.vibecheck_image_analysis_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_image_analysis_cache FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_image_analysis_cache FROM anon, authenticated;

-- =========================================================================
-- vibecheck_video_analysis_cache (TASK-1483.24 — Vision API frame findings cache)
-- =========================================================================

CREATE TABLE IF NOT EXISTS public.vibecheck_video_analysis_cache (
    video_url TEXT PRIMARY KEY,
    frame_findings_payload JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS vibecheck_video_analysis_cache_expires_at_idx
    ON public.vibecheck_video_analysis_cache (expires_at);
ALTER TABLE public.vibecheck_video_analysis_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_video_analysis_cache FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.vibecheck_video_analysis_cache FROM anon, authenticated;

-- =========================================================================
-- Extend vibecheck_jobs_error_code_check for current PDF pipeline errors
-- (TASK-1474.03, TASK-1498.01)
-- =========================================================================
-- Use ALTER ... DROP CONSTRAINT IF EXISTS + ADD inline instead of a DO-block
-- information_schema probe: the probe has a TOCTOU window where a concurrent
-- schema apply can drop the constraint between the EXISTS check and the
-- subsequent DROP, producing a "constraint does not exist" error (codex P2.5).
-- DROP ... IF EXISTS collapses both steps into one atomic, idempotent call.
ALTER TABLE public.vibecheck_jobs
  DROP CONSTRAINT IF EXISTS vibecheck_jobs_error_code_check;

ALTER TABLE public.vibecheck_jobs
  ADD CONSTRAINT vibecheck_jobs_error_code_check
  CHECK (
    error_code IS NULL
        OR error_code IN (
      'invalid_url', 'unsupported_site', 'upstream_error',
      'extraction_failed', 'timeout', 'rate_limited', 'internal',
      'unsafe_url', 'section_failure', 'pdf_too_large',
      'pdf_extraction_failed'
    )
  );

-- =========================================================================
-- Sync vibecheck_jobs_status_check to include 'partial' (TASK-1529)
-- =========================================================================
-- Commit ab7aa1b1 (TASK-1474.29) added 'partial' to the inline CREATE TABLE
-- CHECK definition but never added the ALTER blocks that propagate the change
-- to existing tables. Production Postgres still has the pre-1474.29 constraint,
-- so finalize.py raises CheckViolationError when writing status='partial'.
ALTER TABLE public.vibecheck_jobs
  DROP CONSTRAINT IF EXISTS vibecheck_jobs_status_check;

ALTER TABLE public.vibecheck_jobs
  ADD CONSTRAINT vibecheck_jobs_status_check
  CHECK (status IN ('pending', 'extracting', 'analyzing', 'done', 'partial', 'failed'));

-- =========================================================================
-- Sync vibecheck_jobs_terminal_finished_at to include 'partial' (TASK-1529)
-- =========================================================================
ALTER TABLE public.vibecheck_jobs
  DROP CONSTRAINT IF EXISTS vibecheck_jobs_terminal_finished_at;

ALTER TABLE public.vibecheck_jobs
  ADD CONSTRAINT vibecheck_jobs_terminal_finished_at
  CHECK (
    (status NOT IN ('done', 'partial', 'failed') AND finished_at IS NULL)
    OR (status IN ('done', 'partial', 'failed') AND finished_at IS NOT NULL)
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

-- ============= VIBECHECK FEEDBACK =============

CREATE TABLE IF NOT EXISTS public.vibecheck_feedback (
  id              uuid PRIMARY KEY,
  created_at      timestamptz NOT NULL DEFAULT now(),
  page_path       text NOT NULL,
  user_agent      text NOT NULL,
  referrer        text NOT NULL DEFAULT '',
  uid             uuid NOT NULL,
  bell_location   text NOT NULL,
  initial_type    text NOT NULL CHECK (initial_type IN ('thumbs_up','thumbs_down','message')),
  email           text,
  message         text,
  final_type      text CHECK (final_type IN ('thumbs_up','thumbs_down','message')),
  submitted_at    timestamptz
);
ALTER TABLE public.vibecheck_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vibecheck_feedback FORCE ROW LEVEL SECURITY;
GRANT INSERT, UPDATE, SELECT ON public.vibecheck_feedback TO anon;

DROP POLICY IF EXISTS vibecheck_feedback_anon_insert ON public.vibecheck_feedback;
DROP POLICY IF EXISTS vibecheck_feedback_anon_update ON public.vibecheck_feedback;
DROP POLICY IF EXISTS vibecheck_feedback_anon_write ON public.vibecheck_feedback;
CREATE POLICY vibecheck_feedback_anon_write ON public.vibecheck_feedback
  FOR ALL TO anon USING (true) WITH CHECK (true);

-- No DELETE policy for anon; no separate SELECT policy needed — FOR ALL covers
-- row visibility for UPDATE USING evaluation. service_role bypasses RLS.

CREATE INDEX IF NOT EXISTS vibecheck_feedback_uid_created_idx
  ON public.vibecheck_feedback (uid, created_at DESC);
CREATE INDEX IF NOT EXISTS vibecheck_feedback_bell_location_idx
  ON public.vibecheck_feedback (bell_location);
