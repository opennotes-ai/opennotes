import type { ComponentProps } from "solid-js";
import { cn } from "../../utils";

export function Skeleton(props: ComponentProps<"div">) {
  return (
    <div
      {...props}
      class={cn("animate-pulse rounded-md bg-muted", props.class)}
    />
  );
}

export function SectionSkeleton() {
  return (
    <div class="space-y-4 py-6">
      <Skeleton class="h-6 w-48" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-3/4" />
      <Skeleton class="h-32 w-full" />
    </div>
  );
}
