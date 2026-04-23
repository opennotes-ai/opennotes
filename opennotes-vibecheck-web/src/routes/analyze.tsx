import {
  Show,
  Suspense,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  type Accessor,
} from "solid-js";
import { useSearchParams, A, createAsync, query } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import CachedBadge from "~/components/CachedBadge";
import JobFailureCard from "~/components/JobFailureCard";
import PageFrame from "~/components/PageFrame";
import Sidebar from "~/components/sidebar/Sidebar";
import type {
  ErrorCode,
  JobState,
  SectionSlug,
} from "~/lib/api-client.server";
import { getFrameCompat } from "./analyze.data";

// pollJob lives in api-client.server (Node-only Google auth deps). We wrap it
// in a SolidStart server query so the client bundle gets a thin RPC proxy
// instead of the full Google auth stack. This is the same lift pattern
// analyze.data.ts uses for analyzeUrl/retrySection.
//
// The polling loop itself runs in the browser (setTimeout + reactive signals)
// and mirrors createPollingResource from src/lib/polling.ts; we do not import
// polling.ts directly because it statically pulls api-client.server into the
// client bundle.
const pollJobQuery = query(async (jobId: string): Promise<JobState> => {
  "use server";
  const { pollJob } = await import("~/lib/api-client.server");
  return pollJob(jobId);
}, "vibecheck-poll-job");

const MIN_INTERVAL_MS = 500;
const MAX_INTERVAL_MS = 5000;
const DEFAULT_INTERVAL_MS = 1500;
const MAX_CONSECUTIVE_ERRORS = 3;

function clampInterval(nextPollMs: number | null | undefined): number {
  if (typeof nextPollMs !== "number" || !Number.isFinite(nextPollMs)) {
    return DEFAULT_INTERVAL_MS;
  }
  return Math.min(MAX_INTERVAL_MS, Math.max(MIN_INTERVAL_MS, nextPollMs));
}

function isTerminalStatus(status: JobState["status"] | undefined): boolean {
  return status === "done" || status === "failed";
}

interface PollingHandle {
  state: Accessor<JobState | null>;
  error: Accessor<Error | null>;
  refetch: () => void;
}

function createJobPolling(jobId: Accessor<string>): PollingHandle {
  const [state, setState] = createSignal<JobState | null>(null);
  const [error, setError] = createSignal<Error | null>(null);

  let timerId: ReturnType<typeof setTimeout> | null = null;
  let generation = 0;
  let consecutiveErrors = 0;
  let stopped = false;
  let currentJobId: string | null = null;

  const clearTimer = () => {
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
  };

  const tick = async (gen: number) => {
    if (gen !== generation || stopped || currentJobId === null) return;
    const idAtStart = currentJobId;
    try {
      const result = await pollJobQuery(idAtStart);
      if (gen !== generation || stopped) return;
      consecutiveErrors = 0;
      setError(null);
      setState(result);
      if (isTerminalStatus(result.status)) {
        stopped = true;
        clearTimer();
        return;
      }
      const interval = clampInterval(result.next_poll_ms);
      clearTimer();
      timerId = setTimeout(() => {
        timerId = null;
        void tick(gen);
      }, interval);
    } catch (err: unknown) {
      if (gen !== generation || stopped) return;
      const normalized = err instanceof Error ? err : new Error(String(err));
      consecutiveErrors += 1;
      console.error("analyze: poll failed", normalized);
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        stopped = true;
        clearTimer();
        setError(normalized);
        return;
      }
      const latest = state();
      const interval = clampInterval(latest?.next_poll_ms);
      clearTimer();
      timerId = setTimeout(() => {
        timerId = null;
        void tick(gen);
      }, interval);
    }
  };

  const start = (id: string) => {
    generation += 1;
    consecutiveErrors = 0;
    stopped = false;
    currentJobId = id;
    clearTimer();
    setError(null);
    setState(null);
    const gen = generation;
    void tick(gen);
  };

  createEffect(() => {
    const id = jobId();
    if (!id) {
      generation += 1;
      stopped = true;
      currentJobId = null;
      clearTimer();
      return;
    }
    start(id);
  });

  onCleanup(() => {
    generation += 1;
    stopped = true;
    currentJobId = null;
    clearTimer();
  });

  const refetch = () => {
    const id = currentJobId ?? jobId();
    if (!id) return;
    start(id);
  };

  return { state, error, refetch };
}

const ALL_ERROR_CODES: readonly ErrorCode[] = [
  "invalid_url",
  "unsupported_site",
  "upstream_error",
  "extraction_failed",
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

  const polling = createJobPolling(jobId);

  const jobState = () => polling.state();
  const jobStatus = () => jobState()?.status;
  const jobUrl = () => jobState()?.url ?? pendingUrl();

  const frameCompat = createAsync(async () => {
    const url = jobUrl();
    if (!url) return null;
    return getFrameCompat(url);
  });

  const transportError = () => polling.error();

  const failureProps = createMemo(() => {
    if (pendingError()) {
      return {
        url: pendingUrl(),
        errorCode: pendingError(),
        errorHost: pendingHost() || null,
        errorMessage: null as string | null,
      };
    }
    const s = jobState();
    if (s && s.status === "failed") {
      return {
        url: s.url ?? pendingUrl(),
        errorCode: (s.error_code ?? null) as ErrorCode | null,
        errorHost: s.error_host ?? null,
        errorMessage: s.error_message ?? null,
      };
    }
    if (transportError()) {
      return {
        url: jobUrl(),
        errorCode: "internal" as ErrorCode,
        errorHost: null,
        errorMessage: null as string | null,
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
          <Show when={cachedAt()}>
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
                        {(() => {
                          const fc = frameCompat();
                          const compat =
                            fc && fc.ok
                              ? fc.frameCompat
                              : {
                                  canIframe: true,
                                  blockingHeader: null,
                                  screenshotUrl: null,
                                };
                          return (
                            <PageFrame
                              url={url()}
                              canIframe={compat.canIframe}
                              screenshotUrl={compat.screenshotUrl}
                            />
                          );
                        })()}
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
                  onRetry={handleRetry}
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
                />
              );
            }}
          </Show>
        </Show>
      </main>
    </>
  );
}
