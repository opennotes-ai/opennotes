import type { APIEvent } from "@solidjs/start/server";
import { parseCookieHeader, serializeCookieHeader } from "@supabase/ssr";
import { createClient } from "~/lib/supabase-server";

// CSRF posture: this route is intentionally cookie-only with no token check.
// Safe because Supabase auth cookies default to SameSite=Lax; cross-site form
// posts won't carry the session. If you change cookie attributes, revisit this.
export async function POST(event: APIEvent): Promise<Response> {
  const responseHeaders = new Headers();
  const supabase = createClient(event.request, responseHeaders);

  let cleared = false;
  try {
    const { error } = await supabase.auth.signOut();
    cleared = !error;
    if (error && error.name !== "AuthSessionMissingError") {
      console.warn("signout: unexpected supabase signOut error:", error);
    } else if (error?.name === "AuthSessionMissingError") {
      // Idempotent: no active session means there's nothing to clear.
      cleared = true;
    }
  } catch (err) {
    console.error("signout: supabase signOut threw:", err);
  }

  if (!cleared) {
    // Defensive: ensure any sb-* auth cookies the client sent are expired
    // even if Supabase didn't issue removals through setAll.
    const inbound = parseCookieHeader(event.request.headers.get("Cookie") ?? "");
    for (const { name } of inbound) {
      if (name.startsWith("sb-")) {
        responseHeaders.append(
          "Set-Cookie",
          serializeCookieHeader(name, "", { path: "/", maxAge: 0 }),
        );
      }
    }
  }

  responseHeaders.set("Location", "/");
  return new Response(null, { status: 303, headers: responseHeaders });
}

const methodNotAllowed = (): Response =>
  new Response("Method Not Allowed", {
    status: 405,
    headers: { Allow: "POST" },
  });

export const GET = methodNotAllowed;
export const PUT = methodNotAllowed;
export const PATCH = methodNotAllowed;
export const DELETE = methodNotAllowed;
export const OPTIONS = methodNotAllowed;
