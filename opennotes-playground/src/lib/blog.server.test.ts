import { describe, expect, it, vi, beforeEach } from "vitest";
import type { SupabaseClient } from "@supabase/supabase-js";

vi.mock("./markdown", () => ({
  renderMarkdown: vi.fn((src: string) => `<p>${src}</p>`),
  renderInlineMarkdown: vi.fn((src: string) => src),
}));

import { renderMarkdown } from "./markdown";
import { renderInlineMarkdown } from "./markdown";
import { fetchBlogPosts } from "./blog.server";

function makeRow(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "row-1",
    title: "Test Post",
    slug: "test-post",
    body_markdown: "# Hello",
    published_at: "2026-03-01T00:00:00Z",
    author: null,
    ...overrides,
  };
}

function createMockSupabase(result: { data: unknown[] | null; error: unknown }) {
  const range = vi.fn().mockResolvedValue(result);
  const order = vi.fn(() => ({ range }));
  const not = vi.fn(() => ({ order }));
  const select = vi.fn(() => ({ not }));
  const from = vi.fn(() => ({ select }));
  return {
    client: { from } as unknown as SupabaseClient,
    mocks: { from, select, not, order, range },
  };
}

beforeEach(() => {
  vi.mocked(renderMarkdown).mockClear();
  vi.mocked(renderInlineMarkdown).mockClear();
});

describe("fetchBlogPosts", () => {
  it("queries published posts ordered by published_at DESC", async () => {
    const row = makeRow();
    const { client, mocks } = createMockSupabase({ data: [row], error: null });

    await fetchBlogPosts(client);

    expect(mocks.from).toHaveBeenCalledWith("blog_posts");
    expect(mocks.select).toHaveBeenCalledWith(
      "id, title, slug, body_markdown, published_at, author",
    );
    expect(mocks.not).toHaveBeenCalledWith("published_at", "is", null);
    expect(mocks.order).toHaveBeenCalledWith("published_at", {
      ascending: false,
    });
  });

  it("renders body_markdown to HTML via renderMarkdown", async () => {
    const row = makeRow({ body_markdown: "**bold text**" });
    const { client } = createMockSupabase({ data: [row], error: null });

    const { posts } = await fetchBlogPosts(client);

    expect(renderMarkdown).toHaveBeenCalledWith("**bold text**");
    expect(posts[0].bodyHtml).toBe("<p>**bold text**</p>");
  });

  it("sets hasMore to true when more posts exist beyond the limit", async () => {
    const rows = [
      makeRow({ id: "1", published_at: "2026-03-03T00:00:00Z" }),
      makeRow({ id: "2", published_at: "2026-03-02T00:00:00Z" }),
      makeRow({ id: "3", published_at: "2026-03-01T00:00:00Z" }),
    ];
    const { client } = createMockSupabase({ data: rows, error: null });

    const { posts, hasMore } = await fetchBlogPosts(client, 0, 2);

    expect(hasMore).toBe(true);
    expect(posts).toHaveLength(2);
  });

  it("sets hasMore to false when at the end", async () => {
    const rows = [
      makeRow({ id: "1" }),
      makeRow({ id: "2" }),
    ];
    const { client } = createMockSupabase({ data: rows, error: null });

    const { posts, hasMore } = await fetchBlogPosts(client, 0, 5);

    expect(hasMore).toBe(false);
    expect(posts).toHaveLength(2);
  });

  it("returns empty array when no data", async () => {
    const { client } = createMockSupabase({ data: null, error: null });

    const { posts, hasMore } = await fetchBlogPosts(client);

    expect(posts).toEqual([]);
    expect(hasMore).toBe(false);
  });

  it("maps author through renderMarkdown when present", async () => {
    const row = makeRow({ author: "[Mike](https://example.com)" });
    const { client } = createMockSupabase({ data: [row], error: null });

    const { posts } = await fetchBlogPosts(client);

    expect(renderInlineMarkdown).toHaveBeenCalledWith("[Mike](https://example.com)");
    expect(posts[0].author).toBe("[Mike](https://example.com)");
    expect(posts[0].authorHtml).toBe("[Mike](https://example.com)");
  });

  it("leaves author undefined when null", async () => {
    const row = makeRow({ author: null });
    const { client } = createMockSupabase({ data: [row], error: null });

    const { posts } = await fetchBlogPosts(client);

    expect(posts[0].author).toBeUndefined();
    expect(posts[0].authorHtml).toBeUndefined();
  });

  it("throws when Supabase returns an error", async () => {
    const supaError = { message: "relation not found", code: "42P01" };
    const { client } = createMockSupabase({ data: null, error: supaError });

    await expect(fetchBlogPosts(client)).rejects.toEqual(supaError);
  });
});
