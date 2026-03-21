import type { APIEvent } from "@solidjs/start/server";
import { Feed } from "feed";
import { fetchBlogPosts } from "~/lib/blog.server";

export async function GET(event: APIEvent) {
  const origin = new URL(event.request.url).origin;

  try {
    const { posts } = await fetchBlogPosts(event.locals.supabase, 0, 50);

    const feed = new Feed({
      title: "Open Notes Blog",
      description: "Updates from the Open Notes project",
      id: origin,
      link: origin,
      language: "en",
      copyright: "",
    });

    for (const post of posts) {
      feed.addItem({
        title: post.title,
        id: `${origin}/#${post.slug}`,
        link: `${origin}/#${post.slug}`,
        content: post.bodyHtml,
        date: new Date(post.publishedAt),
        author: post.author ? [{ name: post.author }] : undefined,
      });
    }

    return new Response(feed.rss2(), {
      headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
    });
  } catch {
    return new Response("Internal Server Error", { status: 500 });
  }
}
