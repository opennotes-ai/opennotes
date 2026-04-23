import { For } from "solid-js";

export default function SubjectiveSkeleton() {
  const rows = [0, 1, 2];
  return (
    <ul
      data-testid="skeleton-opinions_sentiments__subjective"
      aria-hidden="true"
      class="space-y-3"
    >
      <For each={rows}>
        {() => (
          <li class="flex items-start gap-2">
            <span
              aria-hidden="true"
              class="skeleton-pulse mt-0.5 inline-block h-4 w-2 shrink-0 rounded-sm bg-muted"
            />
            <div class="flex-1 space-y-1.5">
              <span class="skeleton-pulse block h-3 w-full rounded bg-muted" />
              <span class="skeleton-pulse block h-3 w-4/5 rounded bg-muted" />
            </div>
          </li>
        )}
      </For>
    </ul>
  );
}
