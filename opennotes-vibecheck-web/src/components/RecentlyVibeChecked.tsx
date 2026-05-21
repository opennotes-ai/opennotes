import { For, Show } from "solid-js";
import type { RecentAnalysis } from "~/lib/api-client.server";
import GalleryCard from "./GalleryCard";

interface RecentlyVibeCheckedProps {
  analyses: RecentAnalysis[];
}

export function RecentlyVibeCheckedSkeleton() {
  return (
    <section class="w-full space-y-4">
      <div class="h-6 w-48 animate-pulse rounded bg-muted" />
      <div class="grid grid-cols-1 gap-[33px] md:grid-cols-2">
        <For each={[0, 1, 2]}>
          {() => (
            <div
              style={{ width: "428px", height: "169px", "border-radius": "2px" }}
              class="animate-pulse bg-muted"
            />
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
        <div class="grid grid-cols-1 gap-[33px] md:grid-cols-2">
          <For each={props.analyses}>
            {(item) => (
              <GalleryCard
                href={`/analyze?job=${item.job_id}`}
                title={item.page_title ?? item.source_url}
                snippet={item.preview_description}
                screenshotUrl={item.screenshot_url}
                safetyRecommendation={item.safety_recommendation}
                weatherReport={item.weather_report}
                testid="recent-analysis-card"
              />
            )}
          </For>
        </div>
      </section>
    </Show>
  );
}
