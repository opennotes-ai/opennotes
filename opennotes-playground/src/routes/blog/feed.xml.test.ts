import { describe, expect, it, vi, beforeEach } from "vitest";

const { mockFetchBlogPosts } = vi.hoisted(() => ({
  mockFetchBlogPosts: vi.fn(),
}));

vi.mock("~/lib/blog.server", () => ({
  fetchBlogPosts: mockFetchBlogPosts,
}));

import { GET } from "./feed.xml";

function makePost(overrides: Record<string, unknown> = {}) {
  return {
    id: "post-1",
    title: "Test Post",
    slug: "test-post",
    bodyHtml: "<p>Hello world</p>",
    publishedAt: "2026-03-01T00:00:00Z",
    author: "Alice",
    ...overrides,
  };
}

function makeEvent() {
  return {
    request: new Request("https://example.com/blog/feed.xml"),
    locals: { supabase: {} },
  } as any;
}

beforeEach(() => {
  mockFetchBlogPosts.mockReset();
});

describe("GET /blog/feed.xml", () => {
  it("returns valid RSS XML with Content-Type application/rss+xml", async () => {
    mockFetchBlogPosts.mockResolvedValue({ posts: [], hasMore: false });

    const response = await GET(makeEvent());

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe(
      "application/rss+xml; charset=utf-8",
    );
    const body = await response.text();
    expect(body).toContain("<?xml");
    expect(body).toContain("<rss");
  });

  it("includes channel metadata with title, description, and link", async () => {
    mockFetchBlogPosts.mockResolvedValue({ posts: [], hasMore: false });

    const response = await GET(makeEvent());
    const body = await response.text();

    expect(body).toContain("<title>Open Notes Blog</title>");
    expect(body).toContain("<link>https://example.com</link>");
    expect(body).toContain("<description>");
  });

  it("includes each post as an item with title, link, pubDate, author, and content", async () => {
    const post = makePost({
      title: "My Post",
      slug: "my-post",
      bodyHtml: "<p>Content here</p>",
      publishedAt: "2026-03-15T12:00:00Z",
      author: "Bob",
    });
    mockFetchBlogPosts.mockResolvedValue({ posts: [post], hasMore: false });

    const response = await GET(makeEvent());
    const body = await response.text();

    expect(body).toContain("My Post");
    expect(body).toContain("https://example.com/#my-post");
    expect(body).toContain("Bob");
    expect(body).toContain("<p>Content here</p>");
  });

  it("constructs post URLs from request origin + slug", async () => {
    const post = makePost({ slug: "hello-world" });
    mockFetchBlogPosts.mockResolvedValue({ posts: [post], hasMore: false });

    const event = {
      request: new Request("https://play.opennotes.org/blog/feed.xml"),
      locals: { supabase: {} },
    } as any;

    const response = await GET(event);
    const body = await response.text();

    expect(body).toContain("https://play.opennotes.org/#hello-world");
  });

  it("returns valid RSS with no items when no posts exist", async () => {
    mockFetchBlogPosts.mockResolvedValue({ posts: [], hasMore: false });

    const response = await GET(makeEvent());
    const body = await response.text();

    expect(body).toContain("<rss");
    expect(body).not.toContain("<item>");
  });

  it("returns 500 on error", async () => {
    mockFetchBlogPosts.mockRejectedValue(new Error("db down"));

    const response = await GET(makeEvent());

    expect(response.status).toBe(500);
  });
});
