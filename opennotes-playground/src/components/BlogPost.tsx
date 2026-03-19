import { Show } from "solid-js";
import { formatDate } from "~/lib/format";
import type { BlogPost as BlogPostType } from "~/lib/blog.server";

export default function BlogPost(props: { post: BlogPostType }) {
  return (
    <article class="py-8">
      <h3 class="text-lg font-semibold leading-tight">
        {props.post.title}
      </h3>
      <time class="mt-1 block text-sm text-muted-foreground" datetime={props.post.publishedAt}>
        {formatDate(props.post.publishedAt)}
      </time>
      <Show when={props.post.authorHtml}>
        {(html) => (
          <span class="mt-1 block text-sm text-muted-foreground">
            posted by <span innerHTML={html()} />
          </span>
        )}
      </Show>
      <div class="prose prose-sm mt-3 max-w-none dark:prose-invert" innerHTML={props.post.bodyHtml} />
    </article>
  );
}
