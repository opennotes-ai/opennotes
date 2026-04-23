import { For } from "solid-js";

export default function KnownMisinfoSkeleton() {
  const rows = [0, 1];
  return (
    <ul
      data-testid="skeleton-facts_claims__known_misinfo"
      aria-hidden="true"
      class="space-y-3"
    >
      <For each={rows}>
        {() => (
          <li class="flex items-start gap-2">
            <span class="skeleton-pulse mt-0.5 inline-block h-4 w-4 shrink-0 rounded-sm bg-muted" />
            <div class="flex-1 space-y-1.5">
              <span class="skeleton-pulse block h-3 w-11/12 rounded bg-muted" />
              <span class="skeleton-pulse block h-3 w-3/4 rounded bg-muted" />
            </div>
          </li>
        )}
      </For>
    </ul>
  );
}
