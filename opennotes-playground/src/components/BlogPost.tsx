import { Show } from "solid-js";
import { formatDate } from "~/lib/format";
import type { BlogPost as BlogPostType } from "~/lib/blog.server";

export default function BlogPost(props: { post: BlogPostType }) {
  return (
    <article id={props.post.slug} class="py-8">
      <div class="group relative">
        <a
          href={`#${props.post.slug}`}
          class="absolute -left-6 top-0.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
          aria-label="Link to this post"
        >
          #
        </a>
        <h3 class="text-lg font-semibold leading-tight">
          {props.post.title}
        </h3>
      </div>
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
