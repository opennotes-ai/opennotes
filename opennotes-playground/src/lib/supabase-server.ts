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

export async function getUser() {
  const event = getRequestEvent();
  if (!event) throw new Error("No request event available");
  const supabase = createClient(event.request, event.response.headers);
  const {
    data: { user },
  } = await supabase.auth.getUser();
  return user;
}
