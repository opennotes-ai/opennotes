import type { components } from "~/lib/generated-types";
import { createEffect, createMemo } from "solid-js";
import { useHighlights } from "./HighlightsStoreProvider";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type Divergence = components["schemas"]["Divergence"];

function divergenceTitle(divergence: Divergence): string {
  const direction =
    divergence.direction === "escalated" ? "Escalated" : "Discounted";
  return `${direction}: ${divergence.reason}`;
}

function divergenceSeverity(divergence: Divergence): "info" | "warn" {
  return divergence.direction === "escalated" ? "warn" : "info";
}

export function SafetyHighlightsBridge(props: {
  recommendation: SafetyRecommendation | null;
}): null {
  const highlights = useHighlights();

  const divergences = createMemo(
    () => props.recommendation?.divergences ?? null,
    undefined,
    { equals: (a, b) => JSON.stringify(a) === JSON.stringify(b) },
  );

  createEffect(() => {
    const currentDivergences = divergences() ?? [];
    const mapped = currentDivergences.map((divergence, idx) => ({
      id: `safety-divergence:${idx}`,
      source: "safety-divergence" as const,
      title: divergenceTitle(divergence),
      detail: `${divergence.signal_source}: ${divergence.signal_detail}`,
      severity: divergenceSeverity(divergence),
    }));
    highlights.replaceForSource("safety-divergence", mapped);
  });

  return null;
}
