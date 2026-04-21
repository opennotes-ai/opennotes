import { For, Show } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import type { components } from "~/lib/generated-types";

type SafetyPayload = components["schemas"]["SafetySection"];
type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];

export interface SafetySectionProps {
  safety: SafetyPayload;
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "—";
  return `${Math.round(score * 100)}%`;
}

export default function SafetySection(props: SafetySectionProps) {
  const matches = (): HarmfulContentMatch[] =>
    props.safety?.harmful_content_matches ?? [];

  const flaggedCategories = (match: HarmfulContentMatch): string[] =>
    match.flagged_categories ?? [];

  return (
    <Card
      role="region"
      aria-labelledby="sidebar-safety-heading"
      data-testid="sidebar-safety"
      class="space-y-3 p-4"
    >
      <header class="flex items-baseline justify-between gap-2">
        <h3
          id="sidebar-safety-heading"
          class="flex items-center gap-2 text-sm font-semibold text-foreground"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M8 1l6 2v5c0 4-3 6.5-6 7-3-.5-6-3-6-7V3l6-2z" />
          </svg>
          Safety
        </h3>
        <span
          data-testid="safety-count"
          class="text-xs font-medium text-muted-foreground"
        >
          {matches().length} flagged
        </span>
      </header>

      <Show
        when={matches().length > 0}
        fallback={
          <p
            data-testid="safety-empty"
            class="text-xs text-muted-foreground"
          >
            No harmful-content matches detected.
          </p>
        }
      >
        <ul class="space-y-2">
          <For each={matches()}>
            {(match) => (
              <li class="rounded-md border border-border bg-background p-3 text-xs">
                <div class="flex items-center justify-between gap-2">
                  <div class="flex flex-wrap gap-1">
                    <Show
                      when={flaggedCategories(match).length > 0}
                      fallback={
                        <span
                          data-testid="safety-category"
                          class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                        >
                          flagged
                        </span>
                      }
                    >
                      <For each={flaggedCategories(match)}>
                        {(category) => (
                          <span
                            data-testid="safety-category"
                            class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                          >
                            {category}
                          </span>
                        )}
                      </For>
                    </Show>
                  </div>
                  <span
                    data-testid="safety-max-score"
                    class="font-mono text-[11px] text-muted-foreground"
                  >
                    {formatScore(match.max_score)}
                  </span>
                </div>
                <p class="mt-2 font-mono text-[11px] text-muted-foreground">
                  utterance {match.utterance_id}
                </p>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </Card>
  );
}
