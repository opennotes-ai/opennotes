import { For, Show, Suspense } from "solid-js";
import { createAsync, useParams, useSearchParams } from "@solidjs/router";
import { Meta, Title } from "@solidjs/meta";
import GalleryCard from "~/components/GalleryCard";
import type { InternalRecentAnalysis } from "~/lib/api-client.server";
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
): Promise<InternalRecentAnalysis[]> {
  "use server";
  await assertValidInternalPrefix(prefix);
  return getInternalRecentAnalyses(
    prefix,
    clampInternalGalleryLimit(rawLimit),
  );
}

export function InternalGalleryGrid(props: { analyses: InternalRecentAnalysis[] }) {
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
          class="grid grid-cols-1 sm:grid-cols-2 gap-[33px]"
        >
          <For each={props.analyses}>
            {(item) => (
              <GalleryCard
                href={`/analyze?job=${item.job_id}`}
                title={item.page_title ?? item.source_url}
                snippet={item.preview_description ?? item.source_url}
                screenshotUrl={item.screenshot_url}
                screenshotFallback={
                  <div class="flex h-full w-full items-center justify-center bg-muted text-xs uppercase tracking-wide text-muted-foreground">
                    {item.source_type}
                  </div>
                }
                safetyRecommendation={item.safety_recommendation}
                weatherReport={item.weather_report}
                testid="internal-gallery-card"
              />
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
