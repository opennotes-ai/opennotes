import {
  For,
  Show,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  onMount,
  untrack,
} from "solid-js";
import { useSearchParams, A, useNavigate, revalidate } from "@solidjs/router";
import { Title } from "@solidjs/meta";
import CachedBadge from "~/components/CachedBadge";
import JobFailureCard from "~/components/JobFailureCard";
import PageFrame from "~/components/PageFrame";
import type {
  PreviewMode,
  ResolvedPreviewMode,
} from "~/components/PageFrame";
import Sidebar from "~/components/sidebar/Sidebar";
import { HeadlineSummaryReport } from "~/components/sidebar/reports";
import type { ErrorCode, SectionSlug } from "~/lib/api-client.server";
import { createPollingResource } from "~/lib/polling";
import { resolveHeadline } from "~/lib/headline-fallback";
import {
  getArchiveProbe,
  getScreenshot,
  type ArchiveProbeResult,
  type FrameCompatResult,
} from "./analyze.data";

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

type PreviewSize = "regular" | "large" | "max";
type ArchiveProbeState = "pending" | "available" | "unavailable";

const PREVIEW_SIZE_KEY = "vibecheck:preview-size";
const PREVIEW_MODE_OPTIONS: ReadonlyArray<{
  value: PreviewMode;
  label: string;
}> = [
  { value: "original", label: "Original" },
  { value: "archived", label: "Archived" },
  { value: "screenshot", label: "Screenshot" },
];
const PREVIEW_SIZE_OPTIONS: ReadonlyArray<{
  value: PreviewSize;
  label: string;
}> = [
  { value: "regular", label: "Regular" },
  { value: "large", label: "Large" },
  { value: "max", label: "Max width" },
];

const DEFAULT_FRAME_COMPAT: FrameCompatResult = {
  canIframe: true,
  blockingHeader: null,
  cspFrameAncestors: null,
  screenshotUrl: null,
  archivedPreviewUrl: null,
};
const ORIGINAL_BLOCKED_TIP_ID = "preview-mode-original-tip";
const ORIGINAL_BLOCKED_TIP_TEXT =
  "This page blocks framing — click to attempt anyway";
const ARCHIVE_PROBE_INTERVAL_MS = 5_000;
const ARCHIVE_PROBE_CAP_MS = 300_000;
const ARCHIVE_PROBE_TERMINAL_GRACE_MS = 10_000;
const TERMINAL_JOB_STATUSES = new Set(["done", "partial", "failed"]);

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
  const [previewMode, setPreviewMode] = createSignal<PreviewMode>("original");
  const [resolvedPreviewMode, setResolvedPreviewMode] =
    createSignal<ResolvedPreviewMode>("original");
  const [selectedPreviewMode, setSelectedPreviewMode] =
    createSignal<PreviewMode | null>(null);
  const [previewModeRequestId, setPreviewModeRequestId] = createSignal(0);
  const [previewSize, setPreviewSize] = createSignal<PreviewSize>("regular");
  const [isOriginalBlockedTipHovered, setIsOriginalBlockedTipHovered] =
    createSignal(false);
  const [isOriginalBlockedTipFocused, setIsOriginalBlockedTipFocused] =
    createSignal(false);
  let previewModeJobId = jobId();

  onMount(() => {
    try {
      const saved = window.localStorage.getItem(PREVIEW_SIZE_KEY);
      if (saved === "regular" || saved === "large" || saved === "max") {
        setPreviewSize(saved);
      }
    } catch {
      // localStorage is optional in private/locked-down browser contexts.
    }
  });

  createEffect(() => {
    const currentJobId = jobId();
    if (currentJobId !== previewModeJobId) {
      previewModeJobId = currentJobId;
      setPreviewMode("original");
      setResolvedPreviewMode("original");
      setSelectedPreviewMode(null);
    }
  });

  createEffect(() => {
    if (!jobId() && pendingError() === "invalid_url") {
      navigate("/?error=invalid_url", { replace: true });
    }
  });

  const polling = createPollingResource(jobId);

  const jobState = () => polling.state();
  const jobStatus = () => jobState()?.status;
  const jobUrl = createMemo(() => jobState()?.url ?? pendingUrl());
  const shouldProbePreview = () => Boolean(jobUrl()) && !pendingError();
  const [frameCompat, setFrameCompat] =
    createSignal<FrameCompatResult>(DEFAULT_FRAME_COMPAT);
  const [frameCompatPending, setFrameCompatPending] = createSignal(false);
  const [frameCompatUrl, setFrameCompatUrl] = createSignal("");
  const [frameCompatError, setFrameCompatError] = createSignal<string | null>(
    null,
  );
  const [archiveProbeState, setArchiveProbeState] =
    createSignal<ArchiveProbeState>("pending");

  let frameCompatRequest = 0;
  let archiveTerminalAt: number | null = null;
  let archiveTerminalUrl = "";
  createEffect(() => {
    const url = jobUrl();
    const status = jobStatus();
    if (!url) {
      archiveTerminalAt = null;
      archiveTerminalUrl = "";
      return;
    }
    if (archiveTerminalUrl !== url) {
      archiveTerminalUrl = url;
      archiveTerminalAt = null;
    }
    if (TERMINAL_JOB_STATUSES.has(status ?? "")) {
      archiveTerminalAt ??= Date.now();
    } else {
      archiveTerminalAt = null;
    }
  });

  const applyArchiveProbeResult = (
    result: ArchiveProbeResult,
    url: string,
  ) => {
    setFrameCompatPending(false);
    setFrameCompatUrl(url);
    if (result.ok) {
      setFrameCompat((current) => ({
        ...current,
        canIframe: result.can_iframe,
        blockingHeader: result.blocking_header,
        cspFrameAncestors: result.csp_frame_ancestors,
        archivedPreviewUrl: result.archived_preview_url,
      }));
      if (result.has_archive) {
        setArchiveProbeState("available");
      }
      return;
    }
    if (result.kind === "invalid_url") {
      setFrameCompatError("Preview checks unavailable.");
      setArchiveProbeState("unavailable");
    }
  };

  createEffect(() => {
    const url = jobUrl();
    const shouldProbe = shouldProbePreview();
    const request = ++frameCompatRequest;
    setFrameCompat(DEFAULT_FRAME_COMPAT);
    setFrameCompatUrl("");
    setFrameCompatError(null);
    setArchiveProbeState("pending");
    setFrameCompatPending(shouldProbe);
    setResolvedPreviewMode(url ? "unavailable" : "original");
    if (!url || !shouldProbe) {
      setFrameCompatPending(false);
      return;
    }

    let stopped = false;
    let inFlight = false;
    let interval: ReturnType<typeof setInterval> | null = null;
    const startedAt = Date.now();
    const initialStatus = untrack(jobStatus);
    archiveTerminalUrl = url;
    archiveTerminalAt = TERMINAL_JOB_STATUSES.has(initialStatus ?? "")
      ? Date.now()
      : null;

    const clearProbeInterval = () => {
      if (interval !== null) {
        clearInterval(interval);
        interval = null;
      }
    };
    const stopLoop = () => {
      stopped = true;
      clearProbeInterval();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
    const hasTimedOut = () => Date.now() - startedAt >= ARCHIVE_PROBE_CAP_MS;
    const terminalGraceElapsed = () =>
      archiveTerminalAt !== null &&
      Date.now() - archiveTerminalAt >= ARCHIVE_PROBE_TERMINAL_GRACE_MS;
    const stopUnavailableIfExpired = () => {
      if (hasTimedOut() || terminalGraceElapsed()) {
        setArchiveProbeState("unavailable");
        setFrameCompatPending(false);
        if (frameCompatUrl() !== url) {
          setFrameCompat((current) => ({ ...current, canIframe: false }));
        }
        setFrameCompatUrl(url);
        stopLoop();
        return true;
      }
      return false;
    };
    const probeArchive = async (ignoreVisibility = false) => {
      if (stopped) return;
      if (inFlight) {
        stopUnavailableIfExpired();
        return;
      }
      if (
        !ignoreVisibility &&
        typeof document !== "undefined" &&
        document.visibilityState === "hidden"
      ) {
        stopUnavailableIfExpired();
        return;
      }

      inFlight = true;
      let result: ArchiveProbeResult = { ok: false, kind: "transient_error" };
      try {
        await revalidate(getArchiveProbe.keyFor(url));
        if (stopped || request !== frameCompatRequest) return;
        result = await getArchiveProbe(url);
      } catch (error: unknown) {
        console.warn("vibecheck archive probe failed:", error);
      } finally {
        inFlight = false;
      }
      if (stopped || request !== frameCompatRequest) return;

      applyArchiveProbeResult(result, url);
      if (result.ok && result.has_archive) {
        stopLoop();
        return;
      }
      if (result.ok || result.kind === "transient_error") {
        stopUnavailableIfExpired();
      } else if (result.kind === "invalid_url") {
        stopLoop();
      }
    };
    const scheduleProbeInterval = () => {
      clearProbeInterval();
      interval = setInterval(() => {
        void probeArchive();
      }, ARCHIVE_PROBE_INTERVAL_MS);
    };
    function onVisibilityChange() {
      if (document.visibilityState === "hidden") {
        clearProbeInterval();
        return;
      }
      if (hasTimedOut() && stopUnavailableIfExpired()) {
        return;
      }
      void probeArchive();
      if (!stopped) {
        scheduleProbeInterval();
      }
    }

    void getScreenshot(url)
      .then((screenshotUrl) => {
        if (stopped || request !== frameCompatRequest) return;
        setFrameCompat((current) => ({ ...current, screenshotUrl }));
      })
      .catch((error: unknown) => {
        if (request !== frameCompatRequest) return;
        console.warn("vibecheck screenshot fetch failed:", error);
      });

    document.addEventListener("visibilitychange", onVisibilityChange);
    void probeArchive(true);
    scheduleProbeInterval();

    onCleanup(stopLoop);
  });
  onCleanup(() => {
    frameCompatRequest += 1;
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
          webRiskFindings: s.sidebar_payload?.web_risk?.findings ?? [],
        };
      }
      if (transportError()) {
        return {
          url: jobUrl(),
          errorCode: "internal" as ErrorCode,
          errorHost: null,
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

  const selectPreviewSize = (size: PreviewSize) => {
    setPreviewSize(size);
    try {
      window.localStorage.setItem(PREVIEW_SIZE_KEY, size);
    } catch {
      // Best effort only.
    }
  };

  const selectPreviewMode = (mode: PreviewMode) => {
    setPreviewMode(mode);
    setSelectedPreviewMode(mode);
    setPreviewModeRequestId((id) => id + 1);
  };

  const isPreviewModePressed = (mode: PreviewMode) =>
    !isPreviewLoading() &&
    resolvedPreviewMode() !== "unavailable" &&
    (selectedPreviewMode() ?? resolvedPreviewMode()) === mode;
  const isArchiveFallbackPending = () => {
    const compat = frameCompat();
    return (
      archiveProbeState() === "pending" &&
      (!compat.canIframe ||
        Boolean(compat.blockingHeader) ||
        Boolean(compat.cspFrameAncestors)) &&
      !compat.archivedPreviewUrl &&
      !compat.screenshotUrl
    );
  };
  const isPreviewLoading = () =>
    !jobUrl() ||
    frameCompatPending() ||
    frameCompatUrl() !== jobUrl() ||
    isArchiveFallbackPending();
  const showOriginalBlockedTip = () =>
    !frameCompat().canIframe &&
    (isOriginalBlockedTipHovered() || isOriginalBlockedTipFocused());

  const mainClass = createMemo(() => {
    if (previewSize() === "max") {
      return "mx-auto flex min-h-screen w-full max-w-[min(100vw-2rem,1600px)] flex-col gap-6 px-4 py-8";
    }
    if (previewSize() === "large") {
      return "mx-auto flex min-h-screen w-full max-w-[min(100vw-2rem,1280px)] flex-col gap-6 px-4 py-8";
    }
    return "mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-4 py-8";
  });

  const layoutClass = createMemo(() => {
    if (previewSize() === "large") {
      return "flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,2fr)] lg:gap-8";
    }
    if (previewSize() === "max") {
      return "flex flex-col gap-6 lg:grid lg:grid-cols-1 lg:gap-6";
    }
    return "flex flex-col gap-6 lg:grid lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:gap-8";
  });

  const segmentCornerClass = (index: number, total: number) => {
    if (total <= 1) return "rounded-md";
    if (index === 0) return "rounded-l-md rounded-r-none";
    if (index === total - 1) return "rounded-r-md rounded-l-none";
    return "rounded-none";
  };

  const segmentClass = (isSelected: boolean, corners: string) =>
    isSelected
      ? `${corners} bg-foreground px-3 py-1.5 text-xs font-medium text-background disabled:cursor-not-allowed disabled:opacity-50`
      : `${corners} px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-50`;

  return (
    <>
      <Title>vibecheck — analyzing</Title>
      <main
        data-testid="analyze-main"
        data-archive-probe-state={archiveProbeState()}
        class={mainClass()}
      >
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
                data-preview-size={previewSize()}
                class={layoutClass()}
              >
                <div
                  data-testid="analyze-left-column"
                  class="flex min-w-0 flex-col gap-4"
                >
                  <Show when={jobStatus() === "done" || sidebarPayload()}>
                    <HeadlineSummaryReport
                      headline={resolveHeadline(
                        sidebarPayload()?.headline ?? null,
                        {
                          url: jobUrl(),
                          pageTitle: jobState()?.page_title,
                          recommendation:
                            sidebarPayload()?.safety?.recommendation ?? null,
                        },
                      )}
                    />
                  </Show>
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div
                      data-testid="preview-mode-selector"
                      class="relative flex items-center"
                      role="group"
                      aria-label="Preview mode"
                    >
                      <div class="inline-flex rounded-lg border border-border bg-muted/50 p-1">
                        <For each={PREVIEW_MODE_OPTIONS}>
                          {(option, index) => {
                            const isOriginalBlocked = () =>
                              option.value === "original" &&
                              !frameCompat().canIframe;
                            const isArchivedUnavailable = () =>
                              option.value === "archived" &&
                              archiveProbeState() === "unavailable";
                            return (
                              <button
                                type="button"
                                data-testid={`preview-mode-${option.value}`}
                                class={`${segmentClass(
                                  isPreviewModePressed(option.value),
                                  segmentCornerClass(
                                    index(),
                                    PREVIEW_MODE_OPTIONS.length,
                                  ),
                                )}${isOriginalBlocked() ? " opacity-60" : ""}`}
                                aria-pressed={isPreviewModePressed(
                                  option.value,
                                )}
                                aria-describedby={
                                  isOriginalBlocked()
                                    ? ORIGINAL_BLOCKED_TIP_ID
                                    : undefined
                                }
                                disabled={isArchivedUnavailable()}
                                title={
                                  isArchivedUnavailable()
                                    ? "No archive available for this page"
                                    : undefined
                                }
                                onMouseEnter={() => {
                                  if (isOriginalBlocked()) {
                                    setIsOriginalBlockedTipHovered(true);
                                  }
                                }}
                                onMouseLeave={() => {
                                  setIsOriginalBlockedTipHovered(false);
                                }}
                                onFocus={() => {
                                  if (isOriginalBlocked()) {
                                    setIsOriginalBlockedTipFocused(true);
                                  }
                                }}
                                onBlur={() => {
                                  setIsOriginalBlockedTipFocused(false);
                                }}
                                onClick={() => selectPreviewMode(option.value)}
                              >
                                {option.label}
                              </button>
                            );
                          }}
                        </For>
                      </div>
                      <Show when={!frameCompat().canIframe}>
                        <span
                          id={ORIGINAL_BLOCKED_TIP_ID}
                          data-testid={ORIGINAL_BLOCKED_TIP_ID}
                          role="tooltip"
                          data-visible={
                            showOriginalBlockedTip() ? "true" : "false"
                          }
                          class={
                            showOriginalBlockedTip()
                              ? "pointer-events-none absolute left-0 top-full z-20 mt-2 w-max max-w-64 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs font-medium text-popover-foreground shadow-md"
                              : "sr-only"
                          }
                        >
                          {ORIGINAL_BLOCKED_TIP_TEXT}
                        </span>
                      </Show>
                    </div>
                    <div
                      data-testid="preview-size-selector"
                      class="flex items-center justify-end"
                      role="group"
                      aria-label="Preview size"
                    >
                      <div class="inline-flex rounded-lg border border-border bg-muted/50 p-1">
                        <For each={PREVIEW_SIZE_OPTIONS}>
                          {(option, index) => (
                            <button
                              type="button"
                              class={segmentClass(
                                previewSize() === option.value,
                                segmentCornerClass(
                                  index(),
                                  PREVIEW_SIZE_OPTIONS.length,
                                ),
                              )}
                              aria-pressed={previewSize() === option.value}
                              onClick={() => selectPreviewSize(option.value)}
                            >
                              {option.label}
                            </button>
                          )}
                        </For>
                      </div>
                    </div>
                  </div>
                  <PageFrame
                    url={jobUrl()}
                    loading={isPreviewLoading()}
                    canIframe={frameCompat().canIframe}
                    blockingHeader={frameCompat().blockingHeader}
                    cspFrameAncestors={frameCompat().cspFrameAncestors}
                    archivedPreviewUrl={frameCompat().archivedPreviewUrl}
                    screenshotUrl={frameCompat().screenshotUrl}
                    previewMode={previewMode()}
                    previewModeRequestId={previewModeRequestId()}
                    onResolvedModeChange={(mode) => {
                      setResolvedPreviewMode(mode);
                      if (mode !== selectedPreviewMode()) {
                        setSelectedPreviewMode(null);
                      }
                    }}
                  />
                  <Show when={frameCompatError()}>
                    {(message) => (
                      <p
                        data-testid="frame-compat-warning"
                        class="text-xs text-muted-foreground"
                      >
                        {message()} Showing the page directly.
                      </p>
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
