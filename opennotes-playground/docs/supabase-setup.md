# Supabase Setup Guide

This guide walks through creating and configuring the Supabase project that provides authentication for the OpenNotes Playground.

## Prerequisites

- A Supabase account at [supabase.com](https://supabase.com)
- The playground project cloned locally

## 1. Create the Supabase Project

1. Go to [database.new](https://database.new) to create a new project
2. Configure the project:
   - **Name:** `opennotes-playground`
   - **Region:** US Central (Iowa) / `us-central1` (matches our GCP region)
   - **Database password:** generate a strong password and store it securely
3. Wait for the project to finish provisioning (usually under 2 minutes)

## 2. Get API Credentials

1. In the Supabase dashboard, go to **Project Settings** > **API**
2. Copy these two values into your `.env` file:
   - **Project URL** -> `VITE_SUPABASE_URL` (e.g., `https://abcdefghijk.supabase.co`)
   - **Publishable key** -> `VITE_SUPABASE_PUBLISHABLE_KEY` (the `sb_publishable_...` key from API Keys settings, or legacy `anon` key)

The publishable key is safe to expose in client-side code. It only grants access allowed by Row Level Security policies.

## 3. Enable Email/Password Auth

1. Go to **Authentication** > **Providers**
2. Verify that **Email** provider is enabled (it is by default)
3. Recommended settings:
   - **Confirm email:** enabled for production, can be disabled for local development
   - **Secure email change:** enabled
   - **Double confirm email changes:** enabled for production

## 4. Configure Redirect URLs

The auth callback route at `/auth/callback` handles the OAuth code exchange using `@supabase/ssr`. You must whitelist the redirect URLs.

1. Go to **Authentication** > **URL Configuration**
2. Set the **Site URL** to your primary deployment URL:
   - Production: `https://playground.opennotes.ai`
   - Development: `http://localhost:3100`
3. Add the following to **Redirect URLs**:
   - `http://localhost:3100/auth/callback` (local development)
   - `https://playground.opennotes.ai/auth/callback` (production)

You can use wildcard patterns for preview deployments if needed (e.g., `https://*.playground.opennotes.ai/auth/callback`).

## 5. Row Level Security

RLS is managed via Alembic migrations, not the Supabase dashboard. This ensures policies are version-controlled, reproducible, and consistent across environments.

### Current state

All 41 public tables have RLS + FORCE RLS enabled. 12 policies exist for playground-facing tables (user_profiles, community_servers, community_members, notes, ratings, requests, message_archive, scoring_snapshots, simulation_runs). Server-only tables have RLS enabled with no policies — access is blocked for `anon`/`authenticated` roles while `service_role` bypasses RLS automatically.

### Adding RLS to new tables

When creating a new table, include RLS in the same Alembic migration:

```python
def upgrade() -> None:
    op.create_table("my_table", ...)
    op.execute("ALTER TABLE my_table ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE my_table FORCE ROW LEVEL SECURITY")

    # If playground-facing, add policies:
    op.execute("""
        CREATE POLICY "Members can read my_table" ON my_table
        FOR SELECT TO authenticated
        USING ((SELECT public.is_community_member(community_server_id)))
    """)
```

### Policy patterns

- Wrap `auth.uid()` in a subquery: `(SELECT auth.uid())` — evaluated once, not per-row
- Use `public.is_community_member(community_server_id)` for community-scoped access
- Always scope to `TO authenticated` (not `TO public`)
- For user-owned data: `user_id = (SELECT auth.uid())`

### Auditing RLS status

```sql
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename;
```

## Architecture Notes

The playground uses `@supabase/ssr` with SolidStart for cookie-based server-side authentication:

- **Browser client** (`src/lib/supabase-browser.ts`): Uses `createBrowserClient` for client-side auth state
- **Server client** (`src/lib/supabase-server.ts`): Uses `createServerClient` with cookie parsing/serialization for SSR
- **Middleware** (`src/middleware/index.ts`): Refreshes the auth session on every request via `getUser()`
- **Auth callback** (`src/routes/auth/callback.ts`): Exchanges the OAuth code for a session using `exchangeCodeForSession()`

Both the browser and server clients read `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` from environment variables. The `VITE_` prefix makes them available to client-side code via Vite's `import.meta.env` (SolidStart uses Vinxi, which is built on Vite).

## Adding OAuth Providers (Google, GitHub, etc.)

To add social login providers:

1. Go to **Authentication** > **Providers** in the Supabase dashboard
2. Enable the desired provider (e.g., Google, GitHub, Discord)
3. For each provider:
   - Create an OAuth application in the provider's developer console
   - Copy the **Client ID** and **Client Secret** into the Supabase provider settings
   - Set the OAuth callback URL to: `https://<your-project-ref>.supabase.co/auth/v1/callback`
4. No code changes are needed in the playground. The existing `/auth/callback` route and `@supabase/ssr` cookie handling work with all providers.

To trigger social login from the UI, call:

```typescript
const supabase = createClient();
await supabase.auth.signInWithOAuth({
  provider: "github", // or "google", "discord", etc.
  options: {
    redirectTo: `${window.location.origin}/auth/callback`,
  },
});
```

## Troubleshooting

**Auth callback returns 302 to /login:**
- Verify the redirect URL is whitelisted in Supabase URL Configuration
- Check that `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` are set correctly

**Cookies not being set:**
- The middleware must run on every request to refresh sessions
- Check that `app.config.ts` references the middleware file

**"Invalid API key" errors:**
- Make sure you copied the publishable key (`sb_publishable_...`), not the `service_role` key
- Confirm the environment variables have the `VITE_` prefix
