import { Show, createSignal, onCleanup, onMount } from "solid-js";

export interface PageFrameProps {
  url: string;
  canIframe: boolean;
  screenshotUrl: string | null;
}

const IFRAME_LOAD_TIMEOUT_MS = 5_000;

export default function PageFrame(props: PageFrameProps) {
  const [iframeFailed, setIframeFailed] = createSignal(false);
  const [iframeLoaded, setIframeLoaded] = createSignal(false);

  const showIframe = () =>
    props.canIframe && !iframeFailed();

  const showScreenshot = () =>
    (!props.canIframe || iframeFailed()) && !!props.screenshotUrl;

  let timeoutId: ReturnType<typeof setTimeout> | null = null;

  onMount(() => {
    if (props.canIframe) {
      timeoutId = setTimeout(() => {
        if (!iframeLoaded()) {
          setIframeFailed(true);
        }
      }, IFRAME_LOAD_TIMEOUT_MS);
    }
  });

  onCleanup(() => {
    if (timeoutId) clearTimeout(timeoutId);
  });

  const handleIframeLoad = () => {
    setIframeLoaded(true);
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  const handleIframeError = () => {
    setIframeFailed(true);
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  return (
    <section
      aria-label="Page preview"
      class="relative flex h-full min-h-[60vh] flex-col overflow-hidden rounded-lg border border-border bg-card"
    >
      <Show when={showIframe()}>
        <iframe
          data-testid="page-frame-iframe"
          src={props.url}
          title="Analyzed page"
          sandbox="allow-same-origin allow-scripts"
          referrerpolicy="no-referrer"
          loading="lazy"
          onLoad={handleIframeLoad}
          onError={handleIframeError}
          class="h-full min-h-[60vh] w-full flex-1 border-0 bg-background"
        />
      </Show>

      <Show when={showScreenshot()}>
        <img
          data-testid="page-frame-screenshot"
          src={props.screenshotUrl ?? ""}
          alt={`Screenshot of ${props.url}`}
          class="h-full w-full flex-1 bg-background object-contain object-top"
        />
      </Show>

      <Show when={!showIframe() && !showScreenshot()}>
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
        <span class="truncate" title={props.url}>
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
