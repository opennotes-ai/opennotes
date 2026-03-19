import type { APIEvent } from "@solidjs/start/server";

const MAX_LIMIT = 50;

export async function GET(event: APIEvent) {
  const url = new URL(event.request.url);
  const rawOffset = Number(url.searchParams.get("offset") ?? "0");
  const rawLimit = Number(url.searchParams.get("limit") ?? "10");

  const offset = Number.isFinite(rawOffset) && rawOffset >= 0 ? Math.floor(rawOffset) : 0;
  const limit = Number.isFinite(rawLimit) && rawLimit >= 1
    ? Math.min(Math.floor(rawLimit), MAX_LIMIT)
    : 10;

  try {
    const { fetchBlogPosts } = await import("~/lib/blog.server");
    const result = await fetchBlogPosts(event.locals.supabase, offset, limit);
    return new Response(JSON.stringify(result), {
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return new Response(
      JSON.stringify({ error: "Failed to fetch blog posts" }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
}
