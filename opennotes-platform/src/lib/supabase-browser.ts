import { createBrowserClient } from "@supabase/ssr";

export function createClient() {
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase config: VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY required"
    );
  }
  return createBrowserClient(url, key);
}
