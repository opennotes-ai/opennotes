import { Show, Suspense, createEffect, createMemo } from "solid-js";
import { useSearchParams, A, createAsync, useNavigate } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import CachedBadge from "~/components/CachedBadge";
import JobFailureCard from "~/components/JobFailureCard";
import PageFrame from "~/components/PageFrame";
import Sidebar from "~/components/sidebar/Sidebar";
import type { ErrorCode, SectionSlug } from "~/lib/api-client.server";
import { createPollingResource } from "~/lib/polling";
import { getFrameCompat } from "./analyze.data";

const ALL_ERROR_CODES: readonly ErrorCode[] = [
  "invalid_url",
  "unsafe_url",
  "unsupported_site",
  "upstream_error",
  "extraction_failed",
  "section_failure",
  "timeout",
  "rate_limited",
  "internal",
];

function asErrorCode(raw: string | undefined): ErrorCode | null {
  if (!raw) return null;
  return (ALL_ERROR_CODES as readonly string[]).includes(raw)
    ? (raw as ErrorCode)
    : null;
}

export default function AnalyzePage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const jobId = () =>
    typeof searchParams.job === "string" ? searchParams.job : "";
  const pendingErrorRaw = () =>
    typeof searchParams.pending_error === "string"
      ? searchParams.pending_error
      : "";
  const pendingError = createMemo<ErrorCode | null>(() =>
    asErrorCode(pendingErrorRaw() || undefined),
  );
  const pendingUrl = () =>
    typeof searchParams.url === "string" ? searchParams.url : "";
  const pendingHost = () =>
    typeof searchParams.host === "string" ? searchParams.host : "";
  const cachedHint = () => searchParams.c === "1";

  createEffect(() => {
    if (!jobId() && pendingError() === "invalid_url") {
      navigate("/?error=invalid_url", { replace: true });
    }
  });

  const polling = createPollingResource(jobId);

  const jobState = () => polling.state();
  const jobStatus = () => jobState()?.status;
  const jobUrl = createMemo(() => jobState()?.url ?? pendingUrl());

  const frameCompat = createAsync(async () => {
    const url = jobUrl();
    if (!url) return null;
    return getFrameCompat(url);
  });

  const compat = createMemo(() => {
    const fc = frameCompat();
    return fc && fc.ok
      ? fc.frameCompat
      : { canIframe: true, blockingHeader: null, screenshotUrl: null };
  });

  const transportError = () => polling.error();

  const failureProps = createMemo(() => {
    if (jobId()) {
      const s = jobState();
      if (s && s.status === "failed") {
        return {
          url: s.url ?? pendingUrl(),
          errorCode: (s.error_code ?? null) as ErrorCode | null,
          errorHost: s.error_host ?? null,
          errorMessage: s.error_message ?? null,
          webRiskFindings: s.sidebar_payload?.web_risk?.findings ?? [],
        };
      }
      if (transportError()) {
        return {
          url: jobUrl(),
          errorCode: "internal" as ErrorCode,
          errorHost: null,
          errorMessage: null as string | null,
          webRiskFindings: [],
        };
      }
      return null;
    }
    if (pendingError()) {
      return {
        url: pendingUrl(),
        errorCode: pendingError(),
        errorHost: pendingHost() || null,
        errorMessage: null as string | null,
        webRiskFindings: [],
      };
    }
    return null;
  });

  const showFailure = () => failureProps() !== null;

  const handleRetry = (_slug: SectionSlug) => {
    // RetryButton has already POSTed /retry/{slug} by the time this fires;
    // we just kick polling so the UI flips back through pending/running/done.
    polling.refetch();
  };

  const sidebarPayload = () => jobState()?.sidebar_payload ?? null;
  const isCached = () => jobState()?.cached === true;
  const cachedAt = () => sidebarPayload()?.cached_at ?? null;

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
          <Show when={isCached()}>
            <CachedBadge cachedAt={cachedAt()} />
          </Show>
        </nav>

        <Show
          when={jobId() || pendingError()}
          fallback={
            <div
              data-testid="analyze-empty"
              class="rounded-md border border-border bg-card p-6 text-center"
            >
              <p class="text-sm text-muted-foreground">
                No job provided. Go back and submit a URL to analyze.
              </p>
            </div>
          }
        >
          <Show
            when={showFailure()}
            fallback={
              <div
                data-testid="analyze-layout"
                class="flex flex-col gap-6 lg:grid lg:grid-cols-[3fr_2fr] lg:gap-8"
              >
                <div class="flex min-h-[60vh] flex-col gap-4">
                  <Show
                    when={jobUrl()}
                    fallback={
                      <div class="flex min-h-[60vh] flex-1 items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
                        Preparing analysis&hellip;
                      </div>
                    }
                  >
                    {(url) => (
                      <Suspense
                        fallback={
                          <div class="flex min-h-[60vh] flex-1 items-center justify-center rounded-lg border border-border bg-card text-sm text-muted-foreground">
                            Loading preview&hellip;
                          </div>
                        }
                      >
                        <PageFrame
                          url={url()}
                          canIframe={compat().canIframe}
                          screenshotUrl={compat().screenshotUrl}
                        />
                      </Suspense>
                    )}
                  </Show>
                  <Show when={jobStatus() && jobStatus() !== "done"}>
                    <p
                      data-testid="analyze-status"
                      class="text-xs text-muted-foreground"
                    >
                      Status: {jobStatus()}
                    </p>
                  </Show>
                </div>
                <Sidebar
                  sections={jobState()?.sections}
                  payload={sidebarPayload()}
                  jobId={jobId() || undefined}
                  jobStatus={jobStatus()}
                  onRetry={handleRetry}
                  cachedHint={cachedHint()}
                />
              </div>
            }
          >
            {(_ready) => {
              const f = failureProps()!;
              return (
                <JobFailureCard
                  url={f.url ?? ""}
                  errorCode={f.errorCode}
                  errorHost={f.errorHost}
                  errorMessage={f.errorMessage}
                  webRiskFindings={f.webRiskFindings}
                />
              );
            }}
          </Show>
        </Show>
      </main>
    </>
  );
}
