import type { ComponentProps, JSX } from "solid-js";
import { splitProps } from "solid-js";
import * as SkeletonPrimitive from "@kobalte/core/skeleton";
import { cn } from "../../utils";

const SHIMMER_STYLES = `
@keyframes opennotesSkeletonShimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

[data-opennotes-skeleton] {
  position: relative;
  overflow: hidden;
}

[data-skeleton-shimmer] {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image: linear-gradient(
    90deg,
    transparent 0%,
    color-mix(in oklab, var(--card, white) 55%, transparent) 50%,
    transparent 100%
  );
  transform: translateX(-100%);
  animation: opennotesSkeletonShimmer 1.6s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  [data-skeleton-shimmer] {
    animation: none;
    display: none;
  }
}
`;

export interface SkeletonProps extends ComponentProps<"div"> {
  visible?: boolean;
  radius?: number;
}

export function Skeleton(props: SkeletonProps): JSX.Element {
  const [local, others] = splitProps(props, [
    "class",
    "visible",
    "radius",
    "children",
  ]);
  return (
    <SkeletonPrimitive.Root
      data-opennotes-skeleton=""
      visible={local.visible}
      radius={local.radius}
      class={cn("rounded-md bg-muted", local.class)}
      {...others}
    >
      <style>{SHIMMER_STYLES}</style>
      <span aria-hidden="true" data-skeleton-shimmer="" />
      {local.children}
    </SkeletonPrimitive.Root>
  );
}

export function SectionSkeleton(): JSX.Element {
  return (
    <div class="space-y-4 py-6">
      <Skeleton class="h-6 w-48" />
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-3/4" />
      <Skeleton class="h-32 w-full" />
    </div>
  );
}
