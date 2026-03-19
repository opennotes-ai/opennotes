import type { SupabaseClient } from "@supabase/supabase-js";
import { renderMarkdown } from "./markdown";

export type BlogPost = {
  id: string;
  title: string;
  slug: string;
  bodyHtml: string;
  publishedAt: string;
};

export async function fetchBlogPosts(
  supabase: SupabaseClient,
  offset = 0,
  limit = 10,
): Promise<{ posts: BlogPost[]; hasMore: boolean }> {
  const { data, error } = await supabase
    .from("blog_posts")
    .select("id, title, slug, body_markdown, published_at")
    .not("published_at", "is", null)
    .order("published_at", { ascending: false })
    .range(offset, offset + limit);

  if (error) throw error;
  if (!data) return { posts: [], hasMore: false };

  const hasMore = data.length > limit;
  const rows = hasMore ? data.slice(0, limit) : data;

  const posts: BlogPost[] = rows.map((row) => ({
    id: row.id,
    title: row.title,
    slug: row.slug,
    bodyHtml: renderMarkdown(row.body_markdown),
    publishedAt: row.published_at,
  }));

  return { posts, hasMore };
}
