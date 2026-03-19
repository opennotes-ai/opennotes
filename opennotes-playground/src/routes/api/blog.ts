import type { APIEvent } from "@solidjs/start/server";

export async function GET(event: APIEvent) {
  const url = new URL(event.request.url);
  const offset = Number(url.searchParams.get("offset") ?? "0");
  const limit = Number(url.searchParams.get("limit") ?? "10");
  const { fetchBlogPosts } = await import("~/lib/blog.server");
  const result = await fetchBlogPosts(event.locals.supabase, offset, limit);
  return new Response(JSON.stringify(result), {
    headers: { "Content-Type": "application/json" },
  });
}
