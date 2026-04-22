CREATE TABLE IF NOT EXISTS vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE vibecheck_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_analyses FORCE ROW LEVEL SECURITY;
-- vibecheck-server authenticates with anon_key (no user JWT), so PostgREST
-- runs as role 'anon'. An authenticated-only policy silently blocks every
-- cache write. Grant public (covers anon + authenticated); the only write
-- path is the backend and RLS is belt-and-suspenders here.
DROP POLICY IF EXISTS service_role_full_access ON vibecheck_analyses;
CREATE POLICY vibecheck_analyses_full_access ON vibecheck_analyses
    FOR ALL TO public USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS vibecheck_analyses_expires_at_idx ON vibecheck_analyses(expires_at);
