import type { JSX } from "solid-js";

/**
 * Rendered in the analyze sidebar while `jobStatus === "extracting"` so
 * the user sees motion-bearing feedback before the orchestrator seeds any
 * section slots. Reuses the shared `.skeleton-pulse` keyframe so that
 * when extracting flips to analyzing and the per-slot `running` skeletons
 * take over, the pulse rhythm stays continuous.
 *
 * Suppressed automatically when the job is on a terminal status (done /
 * failed) or when the cache-hint flag pins skeleton opacity to 0 — the
 * caller in Sidebar.tsx gates this component behind a strict
 * `jobStatus === "extracting"` check.
 */
export default function ExtractingIndicator(): JSX.Element {
  return (
    <div
      data-testid="extracting-indicator"
      role="status"
      aria-live="polite"
      class="flex items-center gap-3 rounded-lg border border-border bg-card p-3 text-card-foreground shadow-sm"
    >
      <span
        aria-hidden="true"
        class="skeleton-pulse inline-block h-2 w-2 shrink-0 rounded-full bg-primary"
      />
      <span class="flex-1 text-xs font-medium text-muted-foreground">
        Extracting page content&hellip;
      </span>
      <span aria-hidden="true" class="flex shrink-0 items-center gap-1">
        <span class="skeleton-pulse h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
        <span class="skeleton-pulse h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
        <span class="skeleton-pulse h-1.5 w-1.5 rounded-full bg-muted-foreground/60" />
      </span>
    </div>
  );
}
