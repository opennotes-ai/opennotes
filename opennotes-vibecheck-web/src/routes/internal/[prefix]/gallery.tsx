import { For, Show, Suspense } from "solid-js";
import { createAsync, useParams, useSearchParams } from "@solidjs/router";
import { Meta, Title } from "@solidjs/meta";
import GalleryHoverCard from "~/components/GalleryHoverCard";
import type { RecentAnalysis } from "~/lib/api-client.server";
import { formatWeatherReadout } from "~/lib/weather-labels";
import {
  assertValidInternalPrefix,
  getInternalRecentAnalyses,
} from "./gallery.data";

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 200;

export function clampInternalGalleryLimit(raw: string | undefined): number {
  if (raw === undefined || raw.trim() === "") return DEFAULT_LIMIT;
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return DEFAULT_LIMIT;
  return Math.max(1, Math.min(parsed, MAX_LIMIT));
}

export async function loadInternalGalleryData(
  prefix: string,
  rawLimit: string | undefined,
): Promise<RecentAnalysis[]> {
  "use server";
  await assertValidInternalPrefix(prefix);
  return getInternalRecentAnalyses(
    prefix,
    clampInternalGalleryLimit(rawLimit),
  );
}

export function InternalGalleryGrid(props: { analyses: RecentAnalysis[] }) {
  return (
    <main class="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-4 py-8">
      <header class="space-y-1">
        <h1 class="text-2xl font-semibold tracking-tight">Internal gallery</h1>
      </header>
      <Show
        when={props.analyses.length > 0}
        fallback={<p class="text-sm text-muted-foreground">No analyses found.</p>}
      >
        <section
          data-testid="internal-gallery"
          class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <For each={props.analyses}>
            {(item) => (
              <GalleryHoverCard
                item={item}
                data-testid="internal-gallery-card"
                href={`/analyze?job=${item.job_id}`}
                class="group block overflow-hidden rounded-lg border border-border transition-colors hover:border-foreground/30"
              >
                <div
                  role="img"
                  aria-label={item.page_title ?? item.source_url}
                  class="h-36 w-full"
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
                      <p class="truncate text-[11px] text-muted-foreground">
                        {formatWeatherReadout(weatherReport())}
                      </p>
                    )}
                  </Show>
                </div>
              </GalleryHoverCard>
            )}
          </For>
        </section>
      </Show>
    </main>
  );
}

export default function InternalGalleryPage() {
  const params = useParams<{ prefix: string }>();
  const [searchParams] = useSearchParams();
  const analyses = createAsync(() =>
    loadInternalGalleryData(
      params.prefix,
      typeof searchParams.limit === "string" ? searchParams.limit : undefined,
    ),
  );

  return (
    <>
      <Title>Internal gallery</Title>
      <Meta name="robots" content="noindex,nofollow" />
      <Suspense fallback={<InternalGalleryGrid analyses={[]} />}>
        <InternalGalleryGrid analyses={analyses() ?? []} />
      </Suspense>
    </>
  );
}
