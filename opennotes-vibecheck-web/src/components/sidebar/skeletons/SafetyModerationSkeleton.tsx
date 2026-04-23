export default function SafetyModerationSkeleton() {
  return (
    <div
      data-testid="skeleton-safety__moderation"
      aria-hidden="true"
      class="flex flex-wrap gap-2"
    >
      <span class="skeleton-pulse inline-block h-5 w-16 rounded-full bg-muted" />
      <span class="skeleton-pulse inline-block h-5 w-20 rounded-full bg-muted" />
      <span class="skeleton-pulse inline-block h-5 w-14 rounded-full bg-muted" />
    </div>
  );
}
