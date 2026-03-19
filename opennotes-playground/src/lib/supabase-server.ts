import {
  createServerClient,
  parseCookieHeader,
  serializeCookieHeader,
} from "@supabase/ssr";
import { getRequestEvent } from "solid-js/web";

export function createClient(request: Request, responseHeaders: Headers) {
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase config: VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY required"
    );
  }
  return createServerClient(url, key, {
      cookies: {
        getAll() {
          return parseCookieHeader(
            request.headers.get("Cookie") ?? ""
          ).map(({ name, value }) => ({ name, value: value ?? "" }));
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            responseHeaders.append(
              "Set-Cookie",
              serializeCookieHeader(name, value, options)
            );
          });
        },
      },
    }
  );
}

export function createReadOnlyClient(request: Request) {
  const url = import.meta.env.VITE_SUPABASE_URL;
  const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase config: VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY required"
    );
  }
  return createServerClient(url, key, {
    cookies: {
      getAll() {
        return parseCookieHeader(
          request.headers.get("Cookie") ?? ""
        ).map(({ name, value }) => ({ name, value: value ?? "" }));
      },
      setAll() {},
    },
  });
}

export async function getUser() {
  "use server";
  const event = getRequestEvent();
  if (!event) return null;
  return event.locals.user ?? null;
}
