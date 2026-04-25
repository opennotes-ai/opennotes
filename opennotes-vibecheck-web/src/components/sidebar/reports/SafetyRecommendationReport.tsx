import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

export interface SafetyRecommendationReportProps {
  recommendation?: SafetyRecommendation | null;
}

const LEVEL_CLASSES: Record<SafetyRecommendation["level"], string> = {
  safe: "bg-muted text-muted-foreground",
  caution: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  unsafe: "bg-destructive/10 text-destructive",
};

export default function SafetyRecommendationReport(
  props: SafetyRecommendationReportProps,
): JSX.Element {
  return (
    <Show when={props.recommendation} fallback={null}>
      {(recommendation) => {
        const topSignals = () => recommendation().top_signals ?? [];
        const shownSignals = () => topSignals().slice(0, 3);
        const hiddenCount = () => Math.max(0, topSignals().length - 3);
        const unavailable = () => recommendation().unavailable_inputs ?? [];
        return (
          <section
            data-testid="safety-recommendation-report"
            class="space-y-2 rounded-md border border-border bg-background p-3 text-xs"
          >
            <div class="flex items-center gap-2">
              <span
                data-testid="safety-recommendation-level"
                class={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${LEVEL_CLASSES[recommendation().level]}`}
              >
                {recommendation().level}
              </span>
            </div>
            <p class="leading-relaxed text-foreground">
              {recommendation().rationale}
            </p>
            <Show when={shownSignals().length > 0}>
              <ul class="list-disc space-y-1 pl-4 text-muted-foreground">
                <For each={shownSignals()}>
                  {(signal) => <li>{signal}</li>}
                </For>
                <Show when={hiddenCount() > 0}>
                  <li>+{hiddenCount()} more</li>
                </Show>
              </ul>
            </Show>
            <Show when={unavailable().length > 0}>
              <p class="text-[11px] text-muted-foreground">
                Some analyses did not run: {unavailable().join(", ")}
              </p>
            </Show>
          </section>
        );
      }}
    </Show>
  );
}
