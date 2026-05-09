// CSS thumbnail crop strategy: background-image with background-size: 200% (2× zoom)
// and background-position: top center to capture the upper portion of the page screenshot.
// This avoids a server-side derivative and works with the 15-min signed GCS URL.
// If a CSP is added later, the screenshot host must be included in img-src.

import { For, Show } from "solid-js";
import type { RecentAnalysis } from "~/lib/api-client.server";
import { formatWeatherReadout } from "~/lib/weather-labels";
import GalleryHoverCard from "./GalleryHoverCard";
import { FeedbackBell } from "./feedback/FeedbackBell";

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
      <section data-testid="recently-vibe-checked" class="w-full space-y-4">
        <h2 class="text-sm font-semibold text-muted-foreground">
          Recently vibe checked
        </h2>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <For each={props.analyses}>
            {(item) => (
              <div class="relative pb-8 pr-8">
                <GalleryHoverCard
                  item={item}
                  data-testid="recent-analysis-card"
                  href={`/analyze?job=${item.job_id}`}
                  class="group block overflow-hidden rounded-lg border border-border transition-colors hover:border-foreground/30"
                >
                  <div
                    role="img"
                    aria-label={item.page_title ?? item.source_url}
                    class="h-28 w-full"
                    style={{
                      "background-image": `url(${item.screenshot_url})`,
                      "background-size": "200%",
                      "background-position": "top center",
                      "background-repeat": "no-repeat",
                    }}
                  />
                  <div class="space-y-1 p-3">
                    <p class="line-clamp-2 text-sm font-medium leading-snug">
                      {item.page_title ?? item.source_url}
                    </p>
                    <p class="line-clamp-2 text-xs text-muted-foreground">
                      {item.preview_description}
                    </p>
                    <Show when={item.weather_report}>
                      {(weatherReport) => (
                        <p
                          data-testid="recent-analysis-weather"
                          class="truncate text-[11px] text-muted-foreground"
                        >
                          {formatWeatherReadout(weatherReport())}
                        </p>
                      )}
                    </Show>
                  </div>
                </GalleryHoverCard>
                <FeedbackBell
                  bell_location={`home:recently-vibe-checked:${item.job_id}`}
                  ariaContext={item.page_title ?? item.source_url}
                />
              </div>
            )}
          </For>
        </div>
      </section>
    </Show>
  );
}
