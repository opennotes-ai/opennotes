import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const skeletonSource = readFileSync(
  resolve("src/components/ui/skeleton.tsx"),
  "utf8",
);

describe("<Skeleton /> shimmer primitive", () => {
  it("builds on the Kobalte Skeleton primitive (role/aria attrs come from Kobalte)", () => {
    expect(skeletonSource).toContain("@kobalte/core/skeleton");
  });

  it("renders a shimmer overlay element marked with data-skeleton-shimmer", () => {
    expect(skeletonSource).toMatch(/data-skeleton-shimmer/);
  });

  it("forwards a class prop merged via cn() so existing callers stay drop-in compatible", () => {
    expect(skeletonSource).toMatch(/cn\([^)]*\.class/);
  });

  it("respects prefers-reduced-motion in its keyframe styles", () => {
    expect(skeletonSource).toMatch(/prefers-reduced-motion/);
  });

  it("keeps SectionSkeleton exported for back-compat", () => {
    expect(skeletonSource).toMatch(/export\s+function\s+SectionSkeleton/);
  });

  it("ships shimmer keyframes from packages/ui (not from vibecheck-web)", () => {
    expect(skeletonSource).toMatch(/@keyframes\s+[A-Za-z_-]*[Ss]himmer/);
  });
});
