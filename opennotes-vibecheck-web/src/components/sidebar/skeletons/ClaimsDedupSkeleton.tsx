import { For } from "solid-js";

export default function ClaimsDedupSkeleton() {
  const rows = [0, 1, 2, 3];
  return (
    <ul
      data-testid="skeleton-facts_claims__dedup"
      aria-hidden="true"
      class="space-y-2"
    >
      <For each={rows}>
        {() => (
          <li class="flex items-center gap-2">
            <span class="skeleton-pulse inline-block h-2 w-2 rounded-full bg-muted" />
            <span class="skeleton-pulse inline-block h-3 flex-1 rounded bg-muted" />
            <span class="skeleton-pulse inline-block h-4 w-8 rounded-full bg-muted" />
          </li>
        )}
      </For>
    </ul>
  );
}
