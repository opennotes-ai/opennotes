import type { APIEvent } from "@solidjs/start/server";
import { createClient } from "~/lib/supabase-server";

// CSRF posture: this route is intentionally cookie-only with no token check.
// Safe because Supabase auth cookies default to SameSite=Lax; cross-site form
// posts won't carry the session. If you change cookie attributes, revisit this.
export async function POST(event: APIEvent): Promise<Response> {
  const responseHeaders = new Headers();
  const supabase = createClient(event.request, responseHeaders);
  const { error } = await supabase.auth.signOut();
  if (error) {
    console.warn("supabase.auth.signOut() returned error:", error);
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
