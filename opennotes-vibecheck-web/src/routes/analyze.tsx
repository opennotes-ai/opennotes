import { Show, Suspense } from "solid-js";
import { createAsync, useSearchParams, A } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import LoadingShimmer from "~/components/LoadingShimmer";
import { getAnalysis, type AnalyzeQueryResult } from "./analyze.data";

function AnalysisResult(props: { result: AnalyzeQueryResult }) {
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
        <article class="space-y-4 rounded-md border border-border bg-card p-6">
          <h2 class="text-lg font-semibold">
            {okResult().payload.page_title ?? "Untitled page"}
          </h2>
          <p class="text-sm text-muted-foreground">
            Analysis ready. The full sidebar renders in the next slice.
          </p>
        </article>
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
      <main class="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-4 py-10">
        <nav class="flex items-center justify-between">
          <A
            href="/"
            class="text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            &larr; Analyze a different URL
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
            <section aria-labelledby="analysis-heading" class="space-y-4">
              <div>
                <h1
                  id="analysis-heading"
                  class="text-2xl font-semibold tracking-tight"
                >
                  Analyzing
                </h1>
                <p class="mt-1 break-all text-sm text-muted-foreground">
                  {url()}
                </p>
              </div>

              <Suspense
                fallback={<LoadingShimmer label="Analyzing URL" rows={4} />}
              >
                <Show
                  when={analysis()}
                  fallback={<LoadingShimmer label="Analyzing URL" rows={4} />}
                >
                  {(result) => <AnalysisResult result={result()} />}
                </Show>
              </Suspense>
            </section>
          )}
        </Show>
      </main>
    </>
  );
}
