import { Show, createEffect, createSignal, onCleanup, onMount } from "solid-js";

export type PreviewMode = "original" | "archived" | "screenshot";

export interface PageFrameProps {
  url: string;
  canIframe: boolean;
  blockingHeader?: string | null;
  cspFrameAncestors?: string | null;
  archivedPreviewUrl?: string | null;
  screenshotUrl: string | null;
  previewMode: PreviewMode;
}

const IFRAME_LOAD_TIMEOUT_MS = 20_000;
const ARCHIVE_LOAD_TIMEOUT_MS = 3_000;

export default function PageFrame(props: PageFrameProps) {
  const [iframeFailed, setIframeFailed] = createSignal(false);
  const [iframeLoaded, setIframeLoaded] = createSignal(false);
  const [archivedFailed, setArchivedFailed] = createSignal(false);
  const [archivedLoaded, setArchivedLoaded] = createSignal(false);

  const hasBlockingHint = () =>
    !props.canIframe || !!props.blockingHeader || !!props.cspFrameAncestors;
  const requestedMode = () => props.previewMode;
  const hasArchive = () => !!props.archivedPreviewUrl && !archivedFailed();

  const activePreview = (): PreviewMode | "unavailable" => {
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
    // Original blocked or failed — chain B (Original → Archived → Screenshot)
    if (hasArchive()) return "archived";
    if (props.screenshotUrl) return "screenshot";
    return "unavailable";
  };

  const showIframe = () => !iframeFailed();
  const showOriginalVisible = () => activePreview() === "original";
  const showArchived = () => activePreview() === "archived";
  const showScreenshot = () => activePreview() === "screenshot";

  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let archiveTimeoutId: ReturnType<typeof setTimeout> | null = null;
  let iframeRef: HTMLIFrameElement | undefined;
  let archivedIframeRef: HTMLIFrameElement | undefined;
  let currentUrl = props.url;
  let currentArchiveUrl = props.archivedPreviewUrl ?? null;

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

  const clearArchiveTimeout = () => {
    if (archiveTimeoutId) {
      clearTimeout(archiveTimeoutId);
      archiveTimeoutId = null;
    }
  };

  onMount(() => {
    startLoadTimeout();
  });

  onCleanup(() => {
    clearLoadTimeout();
    clearArchiveTimeout();
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
      startLoadTimeout();
    }
  });

  createEffect(() => {
    if (showArchived() && !archivedLoaded()) {
      clearArchiveTimeout();
      archiveTimeoutId = setTimeout(() => {
        if (!archivedLoaded()) {
          setArchivedFailed(true);
        }
      }, ARCHIVE_LOAD_TIMEOUT_MS);
      return;
    }
    clearArchiveTimeout();
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
        clearArchiveTimeout();
        return;
      }
    } catch {
      // If the browser denies inspection, keep the loaded archive visible.
    }
    setArchivedLoaded(true);
    clearArchiveTimeout();
  };

  const handleArchivedError = () => {
    setArchivedFailed(true);
    clearArchiveTimeout();
  };

  return (
    <section
      aria-label="Page preview"
      class="relative flex h-full min-h-[60vh] w-full min-w-0 max-w-full flex-col overflow-hidden rounded-lg border border-border bg-card"
    >
      <Show when={showIframe()}>
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
          {props.url}
        </span>
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
      </div>
    </section>
  );
}
