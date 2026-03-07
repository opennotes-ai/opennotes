import {
  createServerClient,
  parseCookieHeader,
  serializeCookieHeader,
} from "@supabase/ssr";
import { getRequestEvent } from "solid-js/web";

export function createClient(request: Request, responseHeaders: Headers) {
  return createServerClient(
    import.meta.env.VITE_SUPABASE_URL,
    import.meta.env.VITE_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return parseCookieHeader(request.headers.get("Cookie") ?? "");
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
