import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type HarmfulContentSource = HarmfulContentMatch["source"];

export interface SafetyModerationReportProps {
  matches: HarmfulContentMatch[];
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "—";
  return `${Math.round(score * 100)}%`;
}

const SOURCE_LABELS: Record<HarmfulContentSource, string> = {
  openai: "Moderator A",
  gcp: "Moderator B",
};

export default function SafetyModerationReport(
  props: SafetyModerationReportProps,
) {
  const matches = (): HarmfulContentMatch[] => props.matches ?? [];
  const flaggedCategories = (match: HarmfulContentMatch): string[] =>
    match.flagged_categories ?? [];
  const grouped = createMemo(() => {
    const groups: Array<{
      source: HarmfulContentSource;
      label: string;
      matches: HarmfulContentMatch[];
    }> = [];
    for (const source of ["openai", "gcp"] as const) {
      const sourceMatches = matches().filter((match) => match.source === source);
      if (sourceMatches.length > 0) {
        groups.push({
          source,
          label: SOURCE_LABELS[source],
          matches: sourceMatches,
        });
      }
    }
    return groups;
  });

  return (
    <div data-testid="report-safety__moderation" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        <span data-testid="safety-count">{matches().length} flagged</span>
      </p>
      <Show
        when={matches().length > 0}
        fallback={
          <p data-testid="safety-empty" class="text-xs text-muted-foreground">
            No harmful-content matches detected.
          </p>
        }
      >
        <div class="space-y-3">
          <For each={grouped()}>
            {(group) => (
              <section
                data-testid="safety-provider-group"
                data-source={group.source}
                class="space-y-1.5"
              >
                <p
                  data-testid="safety-provider-label"
                  class="text-[11px] font-semibold text-muted-foreground"
                >
                  {group.label}
                </p>
                <ul class="space-y-2">
                  <For each={group.matches}>
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
                          <Show when={match.source === "openai"}>
                            <span
                              data-testid="safety-max-score"
                              class="font-mono text-[11px] text-muted-foreground"
                            >
                              {formatScore(match.max_score)}
                            </span>
                          </Show>
                        </div>
                        <Show
                          when={match.utterance_text?.trim()}
                          fallback={
                            <p class="mt-2 font-mono text-[11px] text-muted-foreground">
                              utterance {match.utterance_id}
                            </p>
                          }
                        >
                          {(utteranceText) => (
                            <p
                              data-testid="safety-utterance-text"
                              class="mt-2 text-xs leading-relaxed text-foreground"
                            >
                              {utteranceText()}
                            </p>
                          )}
                        </Show>
                      </li>
                    )}
                  </For>
                </ul>
              </section>
            )}
          </For>
        </div>
      </Show>
    </div>
  );
}
