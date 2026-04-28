import type { APIEvent } from "@solidjs/start/server";
import { createClient } from "~/lib/supabase-server";

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

export async function GET(): Promise<Response> {
  return new Response("Method Not Allowed", {
    status: 405,
    headers: { Allow: "POST" },
  });
}
