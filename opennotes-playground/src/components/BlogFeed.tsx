import { createSignal, For, Show } from "solid-js";
import { query, createAsync } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";
import BlogPost from "./BlogPost";
import type { BlogPost as BlogPostType } from "~/lib/blog.server";
import { Button } from "~/components/ui/button";

const getInitialPosts = query(async () => {
  "use server";
  const event = getRequestEvent();
  if (!event) return { posts: [], hasMore: false };
  const { fetchBlogPosts } = await import("~/lib/blog.server");
  return fetchBlogPosts(event.locals.supabase, 0, 10);
}, "blogPosts");

export default function BlogFeed() {
  const initial = createAsync(() => getInitialPosts());
  const [extraPosts, setExtraPosts] = createSignal<BlogPostType[]>([]);
  const [hasMore, setHasMore] = createSignal(true);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal<string | null>(null);

  const allPosts = () => [...(initial()?.posts ?? []), ...extraPosts()];

  const loadMore = async () => {
    setLoading(true);
    setError(null);
    try {
      const offset = allPosts().length;
      const res = await fetch(`/api/blog?offset=${offset}&limit=10`);
      if (!res.ok) throw new Error("Failed to load posts");
      const data = await res.json();
      setExtraPosts((prev) => [...prev, ...data.posts]);
      setHasMore(data.hasMore);
    } catch (e) {
      setError("Failed to load posts.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Show when={initial() !== undefined} fallback={<p class="text-muted-foreground">Loading posts...</p>}>
        <Show
          when={allPosts().length > 0}
          fallback={<p class="text-muted-foreground">No posts yet.</p>}
        >
          <div class="divide-y divide-dashed divide-border">
            <For each={allPosts()}>
              {(post) => <BlogPost post={post} />}
            </For>
          </div>
        </Show>
      </Show>
      <Show when={error()}>
        <p class="mt-4 text-sm text-destructive">{error()}</p>
      </Show>
      <Show when={(initial()?.hasMore ?? false) || hasMore()}>
        <Show when={allPosts().length > 0}>
          <div class="mt-4">
            <Button variant="outline" onClick={loadMore} disabled={loading()}>
              {loading() ? "Loading..." : "Load more"}
            </Button>
          </div>
        </Show>
      </Show>
    </div>
  );
}
