import { createEffect } from "solid-js";
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

  createEffect(() => {
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
