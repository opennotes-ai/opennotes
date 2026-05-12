import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render } from "@solidjs/testing-library";
import { afterEach, describe, expect, it } from "vitest";
import { Skeleton } from "./skeleton";

const skeletonSource = readFileSync(
  resolve("src/components/ui/skeleton.tsx"),
  "utf8",
);

describe("<Skeleton /> shimmer primitive", () => {
  afterEach(() => {
    cleanup();
  });

  it("keeps caller height and width classes without inline sizing overrides", () => {
    const { container } = render(() => <Skeleton class="h-4 w-11/12" />);
    const root = container.querySelector("[data-opennotes-skeleton]");
    expect(root).not.toBeNull();

    const cls = root?.getAttribute("class") ?? "";
    expect(cls).toMatch(/\bh-4\b/);
    expect(cls).toMatch(/\bw-11\/12\b/);
    expect((root as HTMLElement).style.height).toBe("");
    expect((root as HTMLElement).style.width).toBe("");
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

  it("does not wrap css variables in hsl() (theme tokens are oklch — wrapping makes them invalid)", () => {
    expect(skeletonSource).not.toMatch(/hsl\(\s*var\(--muted/);
    expect(skeletonSource).not.toMatch(/hsl\(\s*var\(--card/);
  });

  it("keeps bg-muted in the Skeleton root default class — removing it would render the box transparent", () => {
    expect(skeletonSource).toMatch(/cn\([^)]*bg-muted/);
  });

  it("uses color-mix on var(--card) for the shimmer overlay (theme-aware, oklch-safe)", () => {
    expect(skeletonSource).toMatch(
      /color-mix\(\s*in\s+oklab\s*,\s*var\(--card[^)]*\)\s+\d+%\s*,\s*transparent\s*\)/,
    );
  });
});
