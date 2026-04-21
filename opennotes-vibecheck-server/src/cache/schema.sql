CREATE TABLE IF NOT EXISTS vibecheck_analyses (
    url TEXT PRIMARY KEY,
    sidebar_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
ALTER TABLE vibecheck_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE vibecheck_analyses FORCE ROW LEVEL SECURITY;
CREATE POLICY service_role_full_access ON vibecheck_analyses
    TO authenticated USING (true) WITH CHECK (true);
CREATE INDEX IF NOT EXISTS vibecheck_analyses_expires_at_idx ON vibecheck_analyses(expires_at);
