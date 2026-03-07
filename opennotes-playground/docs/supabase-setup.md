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
   - **anon / public key** -> `VITE_SUPABASE_ANON_KEY` (the `anon` key, not the `service_role` key)

The `anon` key is safe to expose in client-side code. It only grants access allowed by Row Level Security policies.

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
   - Development: `http://localhost:3000`
3. Add the following to **Redirect URLs**:
   - `http://localhost:3000/auth/callback` (local development)
   - `https://playground.opennotes.ai/auth/callback` (production)

You can use wildcard patterns for preview deployments if needed (e.g., `https://*.playground.opennotes.ai/auth/callback`).

## 5. Row Level Security

If you create any playground-specific tables in Supabase (beyond the built-in `auth` schema), enable Row Level Security (RLS) on every table:

1. Go to **Table Editor** > select your table
2. Click **Enable RLS**
3. Add appropriate policies (e.g., "Users can read their own data")

The playground currently uses Supabase only for authentication. The application data (simulations, notes, ratings) lives in the OpenNotes server, accessed via API key.

## Architecture Notes

The playground uses `@supabase/ssr` with SolidStart for cookie-based server-side authentication:

- **Browser client** (`src/lib/supabase-browser.ts`): Uses `createBrowserClient` for client-side auth state
- **Server client** (`src/lib/supabase-server.ts`): Uses `createServerClient` with cookie parsing/serialization for SSR
- **Middleware** (`src/middleware/index.ts`): Refreshes the auth session on every request via `getUser()`
- **Auth callback** (`src/routes/auth/callback.ts`): Exchanges the OAuth code for a session using `exchangeCodeForSession()`

Both the browser and server clients read `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` from environment variables. The `VITE_` prefix makes them available to client-side code via Vite's `import.meta.env`.

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
- Check that `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are set correctly

**Cookies not being set:**
- The middleware must run on every request to refresh sessions
- Check that `app.config.ts` references the middleware file

**"Invalid API key" errors:**
- Make sure you copied the `anon` key, not the `service_role` key
- Confirm the environment variables have the `VITE_` prefix
