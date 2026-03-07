import type { APIEvent } from "@solidjs/start/server";
import { createClient } from "~/lib/supabase-server";

function safeRedirectPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("://")) {
    return "/";
  }
  return value;
}

export async function GET(event: APIEvent) {
  const url = new URL(event.request.url);
  const code = url.searchParams.get("code");
  const next = safeRedirectPath(url.searchParams.get("next"));

  if (code) {
    const responseHeaders = new Headers();
    const supabase = createClient(event.request, responseHeaders);
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      responseHeaders.set("Location", next);
      return new Response(null, { status: 302, headers: responseHeaders });
    }
  }

  return new Response(null, {
    status: 302,
    headers: { Location: "/login" },
  });
}
