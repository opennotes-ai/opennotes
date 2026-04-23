export default function SentimentSkeleton() {
  return (
    <div
      data-testid="skeleton-opinions_sentiments__sentiment"
      aria-hidden="true"
      class="flex h-2 w-full overflow-hidden rounded-full bg-muted"
    >
      <span class="skeleton-pulse block h-full w-2/5 bg-muted-foreground/30" />
      <span class="skeleton-pulse block h-full w-1/5 bg-muted-foreground/20" />
      <span class="skeleton-pulse block h-full w-2/5 bg-muted-foreground/30" />
    </div>
  );
}
