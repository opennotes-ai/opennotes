import { Show, Suspense } from "solid-js";
import { createAsync, useSearchParams, A } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import LoadingShimmer from "~/components/LoadingShimmer";
import PageFrame from "~/components/PageFrame";
import CachedBadge from "~/components/CachedBadge";
import Sidebar from "~/components/sidebar/Sidebar";
import { getAnalysis, type AnalyzeQueryResult } from "./analyze.data";

function AnalysisLayout(props: {
  url: string;
  result: Extract<AnalyzeQueryResult, { ok: true }>;
}) {
  return (
    <div class="space-y-6">
      <header class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0 flex-1">
          <h1 class="truncate text-lg font-semibold tracking-tight text-foreground">
            {props.result.payload.page_title ?? "Untitled page"}
          </h1>
          <p class="mt-0.5 break-all text-xs text-muted-foreground">
            {props.url}
          </p>
        </div>
        <CachedBadge
          cached={props.result.payload.cached}
          cachedAt={props.result.payload.scraped_at}
        />
      </header>

      <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <PageFrame
          url={props.url}
          canIframe={props.result.frameCompat.canIframe}
          screenshotUrl={props.result.frameCompat.screenshotUrl}
        />
        <Sidebar payload={props.result.payload} />
      </div>
    </div>
  );
}

function AnalysisResult(props: { url: string; result: AnalyzeQueryResult }) {
  return (
    <Show
      when={props.result.ok === true ? props.result : null}
      fallback={
        <div
          role="alert"
          class="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive"
        >
          {props.result.ok === false
            ? props.result.message
            : "Analysis failed."}
        </div>
      }
    >
      {(okResult) => (
        <AnalysisLayout url={props.url} result={okResult()} />
      )}
    </Show>
  );
}

export default function AnalyzePage() {
  const [searchParams] = useSearchParams();
  const targetUrl = () =>
    typeof searchParams.url === "string" ? searchParams.url : "";

  const analysis = createAsync<AnalyzeQueryResult | null>(async () => {
    const url = targetUrl();
    if (!url) return null;
    return getAnalysis(url);
  });

  return (
    <>
      <Title>vibecheck — analyzing</Title>
      <main class="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-8">
        <nav class="flex items-center justify-between">
          <A
            href="/"
            class="inline-flex items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            <span aria-hidden="true">&larr;</span>
            <span>vibecheck</span>
            <span aria-hidden="true" class="mx-1 text-muted-foreground/60">
              /
            </span>
            <span>back</span>
          </A>
        </nav>

        <Show
          when={targetUrl()}
          fallback={
            <div class="rounded-md border border-border bg-card p-6 text-center">
              <p class="text-sm text-muted-foreground">
                No URL provided. Go back and submit one to analyze.
              </p>
            </div>
          }
        >
          {(url) => (
            <Suspense
              fallback={<LoadingShimmer label="Analyzing URL" rows={4} />}
            >
              <Show
                when={analysis()}
                fallback={<LoadingShimmer label="Analyzing URL" rows={4} />}
              >
                {(result) => (
                  <AnalysisResult url={url()} result={result()} />
                )}
              </Show>
            </Suspense>
          )}
        </Show>
      </main>
    </>
  );
}
