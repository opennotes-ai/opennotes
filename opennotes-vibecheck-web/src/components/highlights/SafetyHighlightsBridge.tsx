// TODO(task-1609): replace local SafetyRecommendationWithDivergences with generated SafetyRecommendation once divergences field appears in src/lib/generated-types.ts
import { createEffect, createMemo } from "solid-js";
import { useHighlights } from "./HighlightsStoreProvider";

export interface SafetyDivergence {
  reason: string;
  signal_source: string;
  signal_detail: string;
}

export interface SafetyRecommendationWithDivergences {
  level: string;
  rationale: string;
  divergences?: SafetyDivergence[] | null;
}

export function SafetyHighlightsBridge(props: {
  recommendation: SafetyRecommendationWithDivergences | null;
}): null {
  const highlights = useHighlights();

  const divergencesKey = createMemo(
    () => JSON.stringify(props.recommendation?.divergences ?? null),
    undefined,
    { equals: (a, b) => a === b },
  );

  createEffect(() => {
    divergencesKey();
    const divergences = props.recommendation?.divergences ?? [];
    const mapped = divergences.map((d, idx) => ({
      id: `safety-divergence:${idx}`,
      source: "safety-divergence" as const,
      title: d.reason,
      detail: `${d.signal_source}: ${d.signal_detail}`,
      severity: "info" as const,
    }));
    highlights.replaceForSource("safety-divergence", mapped);
  });

  return null;
}
