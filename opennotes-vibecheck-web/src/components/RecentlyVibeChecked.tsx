// CSS thumbnail crop strategy: background-image with background-size: 200% (2× zoom)
// and background-position: top center to capture the upper portion of the page screenshot.
// This avoids a server-side derivative and works with the 15-min signed GCS URL.
// If a CSP is added later, the screenshot host must be included in img-src.

import { For, Show } from "solid-js";
import type { RecentAnalysis } from "~/lib/api-client.server";

interface RecentlyVibeCheckedProps {
  analyses: RecentAnalysis[];
}

export function RecentlyVibeCheckedSkeleton() {
  return (
    <section class="w-full space-y-4">
      <div class="h-6 w-48 animate-pulse rounded bg-muted" />
      <div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <For each={[0, 1, 2]}>
          {() => (
            <div class="overflow-hidden rounded-lg border border-border">
              <div class="h-28 animate-pulse bg-muted" />
              <div class="space-y-2 p-3">
                <div class="h-4 animate-pulse rounded bg-muted" />
                <div class="h-3 animate-pulse rounded bg-muted" />
                <div class="h-3 w-3/4 animate-pulse rounded bg-muted" />
              </div>
            </div>
          )}
        </For>
      </div>
    </section>
  );
}

export default function RecentlyVibeChecked(props: RecentlyVibeCheckedProps) {
  return (
    <Show when={props.analyses.length > 0}>
      <section class="w-full space-y-4">
        <h2 class="text-sm font-semibold text-muted-foreground">
          Recently vibe checked
        </h2>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <For each={props.analyses}>
            {(item) => (
              <a
                href={`/analyze?job=${item.job_id}`}
                class="group overflow-hidden rounded-lg border border-border transition-colors hover:border-foreground/30"
              >
                <div
                  class="h-28 w-full"
                  style={{
                    "background-image": `url(${item.screenshot_url})`,
                    "background-size": "200%",
                    "background-position": "top center",
                    "background-repeat": "no-repeat",
                  }}
                />
                <div class="space-y-1 p-3">
                  <p class="overflow-hidden text-ellipsis whitespace-nowrap text-sm font-medium">
                    {item.page_title ?? item.source_url}
                  </p>
                  <p class="line-clamp-2 text-xs text-muted-foreground">
                    {item.preview_description}
                  </p>
                </div>
              </a>
            )}
          </For>
        </div>
      </section>
    </Show>
  );
}
