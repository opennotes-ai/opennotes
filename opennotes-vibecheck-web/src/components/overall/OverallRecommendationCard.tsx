import { Show, type JSX } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import type { components } from "~/lib/generated-types";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type SafetyLevel = components["schemas"]["SafetyLevel"];

export type OverallVerdict = "pass" | "flag";

export interface OverallRecommendationCardProps {
  recommendation: SafetyRecommendation | null;
  overall?: { verdict: OverallVerdict; reason: string } | null;
}

const PASS_LEVELS: SafetyLevel[] = ["safe", "mild"];

function verdictFromLevel(level: SafetyLevel): OverallVerdict {
  return PASS_LEVELS.includes(level) ? "pass" : "flag";
}

function deriveReason(recommendation: SafetyRecommendation): string | null {
  const signals = recommendation.top_signals;
  if (signals && signals.length > 0) {
    const firstSignal = signals[0]?.trim();
    if (firstSignal) {
      return firstSignal;
    }
  }
  const rationale = recommendation.rationale.trim();
  if (!rationale) {
    return null;
  }
  const firstClause = rationale.split(/[,.]/, 1)[0] ?? rationale;
  const trimmedClause = firstClause.trim();
  if (!trimmedClause) {
    return null;
  }
  return trimmedClause;
}

// TODO: replace derivation with top-level overall-recommendation agent response
// once the server-side overall recommendation agent (upcoming) is integrated.
function deriveOverall(
  recommendation: SafetyRecommendation,
): { verdict: OverallVerdict; reason: string } | null {
  const reason = deriveReason(recommendation);
  if (reason === null) {
    return null;
  }
  return {
    verdict: verdictFromLevel(recommendation.level),
    reason,
  };
}

const VERDICT_CLASSES: Record<OverallVerdict, string> = {
  pass: "bg-muted text-muted-foreground border-border",
  flag: "bg-destructive/5 text-destructive border-destructive/40",
};

export function OverallRecommendationCard(
  props: OverallRecommendationCardProps,
): JSX.Element | null {
  const resolved = (): { verdict: OverallVerdict; reason: string } | null => {
    if (props.overall != null) return props.overall;
    if (props.recommendation != null) return deriveOverall(props.recommendation);
    return null;
  };

  return (
    <Show when={resolved()}>
      {(data) => (
        <Card
          data-testid="overall-recommendation-card"
          class={`flex items-center gap-2 border p-3 text-sm font-semibold ${VERDICT_CLASSES[data().verdict]}`}
        >
          <span data-testid="overall-recommendation-verdict">
            {data().verdict === "pass" ? "Overall: OK." : "Overall: Flag!"}
          </span>
          <span data-testid="overall-recommendation-reason" class="font-normal">
            {data().reason}
          </span>
        </Card>
      )}
    </Show>
  );
}
