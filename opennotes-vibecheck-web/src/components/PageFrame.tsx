import { Show, createEffect, createSignal, onCleanup, onMount } from "solid-js";

export type PreviewMode = "original" | "archived" | "screenshot";
export type ResolvedPreviewMode = PreviewMode | "unavailable";

export interface PageFrameProps {
  url: string;
  loading?: boolean;
  canIframe: boolean;
  blockingHeader?: string | null;
  cspFrameAncestors?: string | null;
  archivedPreviewUrl?: string | null;
  screenshotUrl: string | null;
  previewMode: PreviewMode;
  previewModeRequestId?: number;
  onResolvedModeChange?: (mode: ResolvedPreviewMode) => void;
  onArchivedIframeReady?: (iframe: HTMLIFrameElement) => void;
}

const IFRAME_LOAD_TIMEOUT_MS = 20_000;
const ARCHIVE_LOAD_TIMEOUT_MS = 8_000;
export const FALLBACK_COUNTDOWN_MS = 15_000;

export default function PageFrame(props: PageFrameProps) {
  const [iframeFailed, setIframeFailed] = createSignal(false);
  const [iframeLoaded, setIframeLoaded] = createSignal(false);
  const [archivedFailed, setArchivedFailed] = createSignal(false);
  const [archivedLoaded, setArchivedLoaded] = createSignal(false);
  const [countdownElapsed, setCountdownElapsed] = createSignal(false);
  const [userArmedDeciding, setUserArmedDeciding] = createSignal(false);

  const hasBlockingHint = () =>
    !props.canIframe || !!props.blockingHeader || !!props.cspFrameAncestors;
  const hasUrl = () => props.url.trim().length > 0;
  const requestedMode = () => props.previewMode;
  const hasArchive = () => !!props.archivedPreviewUrl && !archivedFailed();

  let lastHandledPreviewModeRequestId = props.previewModeRequestId ?? 0;
  createEffect(() => {
    const requestId = props.previewModeRequestId ?? 0;
    if (requestId === lastHandledPreviewModeRequestId) return;
    lastHandledPreviewModeRequestId = requestId;
    // User intent must come from an explicit parent click token. Inferring it
    // from a previous previewMode value races Solid's parent feedback effects.
    if (
      requestId > 0 &&
      requestedMode() === "original" &&
      !props.canIframe &&
      (hasArchive() || !!props.screenshotUrl)
    ) {
      setUserArmedDeciding(true);
    } else if (requestedMode() !== "original") {
      setUserArmedDeciding(false);
    }
  });

  const isUserArmedDeciding = () => userArmedDeciding();

  const activePreview = ():
    | PreviewMode
    | "deciding"
    | "loading"
    | "unavailable" => {
    if (props.loading || !hasUrl()) return "loading";
    if (requestedMode() === "screenshot") {
      return props.screenshotUrl ? "screenshot" : "unavailable";
    }
    if (requestedMode() === "archived") {
      if (hasArchive()) return "archived";
      return props.screenshotUrl ? "screenshot" : "unavailable";
    }
    // requestedMode === "original"
    if (!hasBlockingHint() && !iframeFailed()) {
      return "original";
    }
    // SERVER-KNOWN blocked (canIframe=false) on initial / non-armed render:
    // auto-resolve to chain B immediately and skip the deciding interstitial
    // entirely. The user can re-arm deciding by clicking Original after the
    // auto-resolve via the userArmedDeciding signal above.
    if (!props.canIframe && !isUserArmedDeciding()) {
      if (hasArchive()) return "archived";
      if (props.screenshotUrl) return "screenshot";
      return "unavailable";
    }
    // Runtime failure (canIframe=true → iframe.onError / blocked load) OR
    // user-armed escape hatch: keep the existing 15s deciding window.
    if (!countdownElapsed()) {
      return "deciding";
    }
    // Countdown elapsed — chain B (Original → Archived → Screenshot)
    if (hasArchive()) return "archived";
    if (props.screenshotUrl) return "screenshot";
    return "unavailable";
  };

  const showIframe = () => !iframeFailed();
  const showOriginalVisible = () => activePreview() === "original";
  const showArchived = () => activePreview() === "archived";
  const showScreenshot = () => activePreview() === "screenshot";
  const showDeciding = () => activePreview() === "deciding";
  const showLoading = () => activePreview() === "loading";

  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let iframeRef: HTMLIFrameElement | undefined;
  let archivedIframeRef: HTMLIFrameElement | undefined;
  let currentUrl = props.url;
  let currentArchiveUrl = props.archivedPreviewUrl ?? null;
  let lastEmittedResolvedMode: ResolvedPreviewMode | null = null;

  const clearLoadTimeout = () => {
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  const startLoadTimeout = () => {
    clearLoadTimeout();
    timeoutId = setTimeout(() => {
      if (!iframeLoaded()) {
        setIframeFailed(true);
      }
    }, IFRAME_LOAD_TIMEOUT_MS);
  };

  onMount(() => {
    if (hasUrl()) startLoadTimeout();
  });

  onCleanup(() => {
    clearLoadTimeout();
  });

  createEffect(() => {
    const archiveUrl = props.archivedPreviewUrl ?? null;
    if (props.url !== currentUrl || archiveUrl !== currentArchiveUrl) {
      currentUrl = props.url;
      currentArchiveUrl = archiveUrl;
      setIframeFailed(false);
      setIframeLoaded(false);
      setArchivedFailed(false);
      setArchivedLoaded(false);
      setCountdownElapsed(false);
      setUserArmedDeciding(false);
      lastHandledPreviewModeRequestId = props.previewModeRequestId ?? 0;
      lastEmittedResolvedMode = null;
      if (hasUrl()) startLoadTimeout();
    }
  });

  createEffect(() => {
    if (showArchived() && !archivedLoaded()) {
      const archiveTimeoutId = setTimeout(() => {
        if (!archivedLoaded()) {
          setArchivedFailed(true);
        }
      }, ARCHIVE_LOAD_TIMEOUT_MS);
      onCleanup(() => clearTimeout(archiveTimeoutId));
      return;
    }
  });

  createEffect(() => {
    // Countdown effect: arms a single timer EXACTLY when activePreview()
    // would return "deciding" — i.e., (requestedMode==="original") AND
    // (iframeFailed || hasBlockingHint) AND NOT the server-blocked
    // auto-resolve path (canIframe=false and not user-armed).
    //
    // Equivalent simplified form: requestedMode==="original" AND
    // (iframeFailed || hasBlockingHint) AND (canIframe || userArmedDeciding).
    //
    // The (canIframe || userArmedDeciding) clause is what makes the timer
    // arm for the canIframe=true + cspFrameAncestors/blockingHeader case
    // (regression caught in code review), while still skipping the timer
    // on the canIframe=false initial-render auto-resolve path.
    const decidingTriggerActive =
      hasUrl() &&
      requestedMode() === "original" &&
      (iframeFailed() || hasBlockingHint()) &&
      (props.canIframe || isUserArmedDeciding());
    if (!decidingTriggerActive) {
      setCountdownElapsed(false);
      return;
    }
    setCountdownElapsed(false);
    const id = setTimeout(
      () => setCountdownElapsed(true),
      FALLBACK_COUNTDOWN_MS,
    );
    onCleanup(() => clearTimeout(id));
  });

  createEffect(() => {
    // AC #4: emit the resolved mode upstream from a createEffect, never from
    // inside activePreview() or render predicates. Skip "deciding" so the
    // parent only sees real, renderable modes.
    const resolved = activePreview();
    if (resolved === "deciding" || resolved === "loading") return;
    if (resolved === lastEmittedResolvedMode) return;
    lastEmittedResolvedMode = resolved;
    props.onResolvedModeChange?.(resolved);
  });

  createEffect(() => {
    if (!showArchived() || !archivedLoaded() || !archivedIframeRef) return;
    props.onArchivedIframeReady?.(archivedIframeRef);
  });

  const classifyLoadedIframe = (): "blocked" | "rendered" | "unknown" => {
    if (!iframeRef) return "unknown";
    try {
      const doc = iframeRef.contentDocument;
      if (!doc) return "unknown";
      const href = doc.location?.href ?? "";
      const body = doc.body;
      const childCount = body?.children?.length ?? 0;
      const bodyText = body?.textContent?.trim() ?? "";
      const title = doc.title?.trim() ?? "";
      if (
        (href === "" || href === "about:blank") &&
        childCount === 0 &&
        !bodyText &&
        !title
      ) {
        return "blocked";
      }
      return "rendered";
    } catch {
      return "rendered";
    }
  };

  const handleIframeLoad = () => {
    const classification = classifyLoadedIframe();
    if (classification === "blocked") {
      setIframeFailed(true);
      // Intentionally do NOT call setIframeLoaded(true) or clearLoadTimeout —
      // the timeout safety net (startLoadTimeout) checks !iframeLoaded() and
      // remains active to backstop a future false-negative classification.
      return;
    }
    setIframeLoaded(true);
    clearLoadTimeout();
  };

  const handleIframeError = () => {
    setIframeFailed(true);
    clearLoadTimeout();
  };

  const handleArchivedLoad = () => {
    try {
      const doc = archivedIframeRef?.contentDocument;
      const bodyText = doc?.body?.textContent?.trim() ?? "";
      const childCount = doc?.body?.children?.length ?? 0;
      const title = doc?.title?.trim() ?? "";
      if (!bodyText && childCount === 0 && !title) {
        setArchivedFailed(true);
        return;
      }
    } catch {
      // If the browser denies inspection, keep the loaded archive visible.
    }
    setArchivedLoaded(true);
    if (archivedIframeRef) {
      props.onArchivedIframeReady?.(archivedIframeRef);
    }
  };

  const handleArchivedError = () => {
    setArchivedFailed(true);
  };

  return (
    <section
      aria-label="Page preview"
      class="relative flex h-full min-h-[60vh] w-full min-w-0 max-w-full flex-col overflow-hidden rounded-lg border border-border bg-card"
    >
      <Show when={hasUrl() && showIframe()}>
        <iframe
          data-testid="page-frame-iframe"
          src={props.url}
          title="Analyzed page"
          sandbox="allow-same-origin allow-scripts"
          referrerpolicy="no-referrer"
          loading="lazy"
          ref={iframeRef}
          aria-hidden={showOriginalVisible() ? undefined : "true"}
          inert={showOriginalVisible() ? undefined : true}
          onLoad={handleIframeLoad}
          onError={handleIframeError}
          class={
            showOriginalVisible()
              ? "h-full min-h-[60vh] w-full flex-1 border-0 bg-background"
              : "pointer-events-none absolute inset-0 h-full min-h-[60vh] w-full flex-1 border-0 bg-background opacity-0"
          }
        />
      </Show>

      <Show when={showLoading()}>
        <div
          data-testid="page-frame-loading"
          role="status"
          aria-live="polite"
          class="flex min-h-[60vh] flex-1 items-center justify-center p-8 text-center"
        >
          <p class="text-sm text-muted-foreground">
            Preparing analysis&hellip;
          </p>
        </div>
      </Show>

      <Show when={showArchived()}>
        <iframe
          data-testid="page-frame-archived-iframe"
          src={props.archivedPreviewUrl ?? ""}
          title="Archived page"
          sandbox="allow-same-origin"
          referrerpolicy="no-referrer"
          loading="lazy"
          ref={archivedIframeRef}
          onLoad={handleArchivedLoad}
          onError={handleArchivedError}
          class="h-full min-h-[60vh] w-full flex-1 border-0 bg-background"
        />
      </Show>

      <Show when={showScreenshot()}>
        <div class="min-h-0 min-w-0 flex-1 overflow-auto bg-background">
          <img
            data-testid="page-frame-screenshot"
            src={props.screenshotUrl ?? ""}
            alt={`Screenshot of ${props.url}`}
            class="block max-w-none"
          />
        </div>
      </Show>

      <Show when={showDeciding()}>
        <div
          data-testid="page-frame-deciding"
          role="status"
          aria-live="polite"
          class="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center"
        >
          <p class="text-sm text-foreground">
            This page prevents being loaded in a frame. Please select Archived
            or Screenshot above.
          </p>
          <p class="text-xs text-muted-foreground">Auto-switching in ~15s.</p>
          <div
            class="h-1 w-full max-w-xs overflow-hidden rounded-full bg-muted"
            aria-hidden="true"
          >
            <div
              data-testid="page-frame-deciding-progress"
              class="h-full bg-primary"
              style={{
                animation: `pageFrameDecidingProgress ${FALLBACK_COUNTDOWN_MS}ms linear forwards`,
              }}
            />
          </div>
        </div>
      </Show>

      <Show when={activePreview() === "unavailable"}>
        <div
          data-testid="page-frame-unavailable"
          class="flex flex-1 items-center justify-center p-8 text-center"
        >
          <p class="text-sm text-muted-foreground">
            Preview unavailable for this page.
          </p>
        </div>
      </Show>

      <div class="flex items-center justify-between gap-2 border-t border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <span class="min-w-0 flex-1 truncate" title={props.url}>
          {props.url || "Preparing preview"}
        </span>
        <Show when={hasUrl()}>
          <a
            href={props.url}
            target="_blank"
            rel="noreferrer noopener"
            class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-foreground hover:bg-accent hover:text-accent-foreground"
          >
            Open original
            <svg
              aria-hidden="true"
              viewBox="0 0 16 16"
              width="12"
              height="12"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M6 3H3v10h10v-3" />
              <path d="M10 2h4v4" />
              <path d="M14 2l-6 6" />
            </svg>
          </a>
        </Show>
      </div>
    </section>
  );
}
