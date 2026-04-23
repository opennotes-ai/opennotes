export default function ScdSkeleton() {
  return (
    <div
      data-testid="skeleton-tone_dynamics__scd"
      aria-hidden="true"
      class="space-y-4"
    >
      <div class="space-y-1.5">
        <div class="skeleton-pulse h-3 w-1/3 rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-full rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-11/12 rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-4/5 rounded bg-muted" />
      </div>
      <div class="space-y-1.5">
        <div class="skeleton-pulse h-3 w-2/5 rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-full rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-10/12 rounded bg-muted" />
        <div class="skeleton-pulse h-3 w-3/4 rounded bg-muted" />
      </div>
    </div>
  );
}
