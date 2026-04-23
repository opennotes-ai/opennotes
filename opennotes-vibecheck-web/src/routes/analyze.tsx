import { Show } from "solid-js";
import { useSearchParams, A } from "@solidjs/router";
import { Title } from "@solidjs/meta";

export default function AnalyzePage() {
  const [searchParams] = useSearchParams();
  const jobId = () =>
    typeof searchParams.job === "string" ? searchParams.job : "";
  const pendingError = () =>
    typeof searchParams.pending_error === "string"
      ? searchParams.pending_error
      : "";
  const pendingUrl = () =>
    typeof searchParams.url === "string" ? searchParams.url : "";

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
          when={pendingError() || jobId()}
          fallback={
            <div class="rounded-md border border-border bg-card p-6 text-center">
              <p class="text-sm text-muted-foreground">
                No job provided. Go back and submit a URL to analyze.
              </p>
            </div>
          }
        >
          <Show
            when={pendingError()}
            fallback={
              <div
                data-testid="analyze-placeholder"
                class="rounded-md border border-border bg-card p-6"
              >
                <p class="text-sm text-muted-foreground">
                  Analyzing job {jobId()}&hellip;
                </p>
              </div>
            }
          >
            {(code) => (
              <div
                role="alert"
                data-testid="analyze-pending-error"
                class="rounded-md border border-destructive/50 bg-destructive/5 p-4 text-sm text-destructive"
              >
                <p>
                  {code()}: couldn&rsquo;t start analysis for{" "}
                  <span class="break-all">{pendingUrl()}</span>
                </p>
              </div>
            )}
          </Show>
        </Show>
      </main>
    </>
  );
}
