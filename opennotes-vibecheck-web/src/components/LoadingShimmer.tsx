import { For } from "solid-js";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";

export interface LoadingShimmerProps {
  rows?: number;
  label?: string;
}

export default function LoadingShimmer(props: LoadingShimmerProps) {
  const rowCount = () => props.rows ?? 4;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={props.label ?? "Analyzing URL"}
      class="w-full space-y-4"
    >
      <Skeleton class="h-6 w-2/3" />
      <Skeleton class="h-4 w-1/2" />
      <div class="mt-6 space-y-3">
        <For each={Array.from({ length: rowCount() })}>
          {() => (
            <div class="rounded-md border border-border bg-card p-4">
              <Skeleton class="h-4 w-1/3" />
              <Skeleton class="mt-3 h-3 w-full" />
              <Skeleton class="mt-2 h-3 w-5/6" />
            </div>
          )}
        </For>
      </div>
      <span class="sr-only">{props.label ?? "Analyzing URL"}</span>
    </div>
  );
}
