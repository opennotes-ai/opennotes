import type { JSX } from "solid-js";

export default function LoadingSavedAnalysis(): JSX.Element {
  return (
    <div
      data-testid="loading-saved-analysis"
      role="status"
      aria-live="polite"
      class="flex min-h-[60vh] items-center justify-center rounded-lg border border-border bg-card p-6 text-card-foreground shadow-sm"
    >
      <div class="flex items-center gap-3">
        <span
          aria-hidden="true"
          class="skeleton-pulse inline-block h-2 w-2 shrink-0 rounded-full bg-primary"
        />
        <span class="text-sm font-medium text-muted-foreground">
          Loading analysis&hellip;
        </span>
      </div>
    </div>
  );
}
