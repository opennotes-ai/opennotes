# exec_sql Bootstrap Runbook

`src/cache/schema.sql` is applied at server startup through the Supabase
PostgREST RPC `public.exec_sql(sql text)`. A fresh Supabase project cannot
create that function through itself, so it must be seeded once (by a human
operator or CI) before the first deploy. Later deploys refresh the function
definition from `schema.sql` by calling it through itself.

`exec_sql` stays owned by `postgres` for this bootstrap window so subsequent
self-applies can re-issue every `CREATE OR REPLACE`, `ALTER TABLE ENABLE RLS`,
`ALTER FUNCTION OWNER TO postgres`, `REVOKE`, and `cron.schedule` call without
ownership-mismatch failures. The security boundary is the `EXECUTE` grant: only
`service_role` can call `exec_sql`, and `service_role` already bypasses RLS on
the same Supabase project. A separate non-superuser owner does not raise the
security floor here. TASK-1490.20 tracks removal of this stop-gap once Alembic
owns vibecheck schema changes.

## §1 One-time exec_sql bootstrap

Paste this exact SQL into the Supabase SQL Editor for your target environment.

```sql
SET LOCAL lock_timeout = '30s';
SELECT pg_advisory_xact_lock(1490, hashtext('schema_apply')::int);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'vibecheck_schema_admin') THEN
        CREATE ROLE vibecheck_schema_admin;
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT has_schema_privilege('vibecheck_schema_admin', 'public', 'CREATE') THEN
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
SET search_path = public, pg_temp
AS $$
BEGIN
    RAISE LOG 'vibecheck exec_sql apply length=% hash=%', length(sql), md5(sql);
    EXECUTE sql;
END;
$$;
COMMENT ON FUNCTION public.exec_sql(text) IS
    'TEMPORARY TASK-1490.20: service-role-only schema bootstrap; postgres-owned so re-apply via exec_sql can ALTER TABLE/FUNCTION owned by postgres without InsufficientPrivilege. search_path=public to allow unqualified CREATE TABLE/ALTER TABLE in schema.sql. Remove once Alembic owns vibecheck changes (TASK-1490.20).';
REVOKE ALL ON FUNCTION public.exec_sql(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.exec_sql(text) TO service_role;
```

Verify the function was created correctly:

```sql
SELECT
    p.proname,
    pg_get_function_identity_arguments(p.oid) AS args,
    pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef,
    p.proconfig,
    array_to_string(p.proacl, ',') AS proacl
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname = 'exec_sql';
```

Expected: one row with `args = sql text`, `owner = postgres`,
`prosecdef = true`, `proconfig = {search_path=public, pg_temp}`, and
`proacl` showing `service_role=X` without `PUBLIC=X`, `anon=X`, or
`authenticated=X`.

This bootstrap is one-time only; subsequent deploys refresh the function
definition through itself via `_apply_schema` at startup.

## §2 Schema drift audit

Run the catalog-backed audit before any `schema.sql` deploy, after rollout,
and during monthly drift sweeps:

```bash
cd opennotes/opennotes-vibecheck-server
uv run --extra audit python scripts/audit_vibecheck_schema.py \
    --report-path /tmp/vibecheck-schema-audit.md
```

Exit codes:

- `0`: no drift found.
- `1`: at least one expected table, column, index, constraint, RLS flag,
  policy, cron job, or function is missing or mismatched.
- `2`: audit could not parse or connect.

Resolve additive drift by applying idempotent SQL in the Supabase SQL editor
and adding the same DDL to `src/cache/schema.sql`. Destructive drift needs a
separate task with a rollback plan. Re-run the audit until it exits `0`.

## §3 Schema-apply failure recovery

`_apply_schema` logs at `ERROR` with a traceback and re-raises. Cloud Run
rejects the new revision if startup cannot apply `schema.sql`.

Focused Cloud Logging query:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   resource.labels.service_name="opennotes-vibecheck-server"
   severity="ERROR"
   textPayload:"vibecheck schema apply via exec_sql RPC failed"' \
  --project=open-notes-core \
  --limit=20 \
  --format=json
```

If a no-traffic canary revision fails with this signal, do not shift traffic.
Fix the reported SQL or bootstrap issue, redeploy a new no-traffic revision,
and rerun §2.

Rollback traffic to the previous healthy revision:

```bash
gcloud run services update-traffic opennotes-vibecheck-server \
  --to-revisions=<previous-revision>=100 \
  --region=us-central1 \
  --project=open-notes-core
```

Schema failures show the `_apply_schema` message above. Generic startup
failures (import errors, missing env vars, DB-pool connection issues) will not
match that query; inspect the revision logs without the message filter for
those cases.
