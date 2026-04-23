export default function FlashpointSkeleton() {
  return (
    <div
      data-testid="skeleton-tone_dynamics__flashpoint"
      aria-hidden="true"
      class="space-y-2"
    >
      <div class="skeleton-pulse h-4 w-5/6 rounded bg-muted" />
      <div class="skeleton-pulse h-4 w-2/3 rounded bg-muted" />
      <div class="skeleton-pulse h-4 w-3/4 rounded bg-muted" />
    </div>
  );
}
