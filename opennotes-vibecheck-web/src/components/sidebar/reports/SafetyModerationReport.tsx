import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import { categoryColor, categoryColorClasses } from "~/lib/category-colors";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type HarmfulContentSource = HarmfulContentMatch["source"];
type SafetyMatchGroup = {
  key: string;
  parent: HarmfulContentMatch;
  chunkMatches: HarmfulContentMatch[];
};

export interface SafetyModerationReportProps {
  matches: HarmfulContentMatch[];
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "—";
  return `${Math.round(score * 100)}%`;
}

const SOURCE_LABELS: Record<HarmfulContentSource, string> = {
  openai: "OpenAI Moderation",
  gcp: "Google Natural Language Moderation",
};

function isChunkMatch(match: HarmfulContentMatch): boolean {
  return match.chunk_idx !== null && match.chunk_idx !== undefined;
}

function matchGroupKey(match: HarmfulContentMatch): string {
  return `${match.source}:${String(match.utterance_id)}`;
}

function groupMatches(matches: HarmfulContentMatch[]): SafetyMatchGroup[] {
  const byKey = new Map<string, HarmfulContentMatch[]>();
  for (const match of matches) {
    const key = matchGroupKey(match);
    byKey.set(key, [...(byKey.get(key) ?? []), match]);
  }
  return Array.from(byKey.entries()).map(([key, group]) => {
    const aggregate = group.find(
      (match) => !isChunkMatch(match) && (match.chunk_count ?? 1) > 1,
    );
    const parent = aggregate ?? group.find((match) => !isChunkMatch(match)) ?? group[0];
    const chunkMatches = group
      .filter((match) => isChunkMatch(match) && match !== parent)
      .sort((a, b) => (a.chunk_idx ?? 0) - (b.chunk_idx ?? 0));
    return { key, parent, chunkMatches };
  });
}

function MatchCard(props: {
  match: HarmfulContentMatch;
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
  child?: boolean;
}) {
  const flaggedCategories = (match: HarmfulContentMatch): string[] =>
    match.flagged_categories ?? [];
  return (
    <div
      data-testid={props.child ? "safety-chunk-row" : "safety-parent-row"}
      data-utterance-id={String(props.match.utterance_id)}
      data-chunk-idx={props.match.chunk_idx ?? ""}
      class={`rounded-md border border-border bg-background p-3 text-xs ${
        props.child ? "ml-3 border-dashed bg-muted/30" : ""
      }`}
    >
      <div class="flex items-center justify-between gap-2">
        <div class="flex flex-wrap gap-1">
          <Show
            when={flaggedCategories(props.match).length > 0}
            fallback={
              (() => {
                const color = categoryColor("flagged", undefined);
                return (
                  <span
                    data-testid="safety-category"
                    data-color={color}
                    class={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${categoryColorClasses(color)}`}
                  >
                    flagged
                  </span>
                );
              })()
            }
          >
            <For each={flaggedCategories(props.match)}>
              {(category) => {
                const score = props.match.scores?.[category] ?? 1;
                const color = categoryColor(category, score);
                return (
                  <span
                    data-testid="safety-category"
                    data-color={color}
                    class={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${categoryColorClasses(color)}`}
                  >
                    {category}
                  </span>
                );
              }}
            </For>
          </Show>
        </div>
        <Show when={props.match.source === "openai"}>
          <span
            data-testid="safety-max-score"
            class="font-mono text-[11px] text-muted-foreground"
          >
            {formatScore(props.match.max_score)}
          </span>
        </Show>
      </div>
      <Show
        when={props.match.utterance_text?.trim()}
        fallback={
          <p class="mt-2 font-mono text-[11px] text-muted-foreground">
            source{" "}
            <UtteranceRef
              utteranceId={String(props.match.utterance_id)}
              chunkIdx={props.match.chunk_idx}
              chunkCount={props.match.chunk_count}
              onClick={props.onUtteranceClick ?? (() => undefined)}
              disabled={!props.canJumpToUtterance || !props.onUtteranceClick}
              testId="safety-utterance-ref"
            />
          </p>
        }
      >
        {(utteranceText) => (
          <div class="mt-2">
            <ExpandableText
              text={utteranceText()}
              lines={2}
              testId="safety-utterance-text"
              class="text-xs leading-relaxed text-foreground"
            />
            <p class="mt-1 font-mono text-[11px] text-muted-foreground">
              source{" "}
              <UtteranceRef
                utteranceId={String(props.match.utterance_id)}
                chunkIdx={props.match.chunk_idx}
                chunkCount={props.match.chunk_count}
                onClick={props.onUtteranceClick ?? (() => undefined)}
                disabled={!props.canJumpToUtterance || !props.onUtteranceClick}
                testId="safety-utterance-ref"
              />
            </p>
          </div>
        )}
      </Show>
    </div>
  );
}

export default function SafetyModerationReport(
  props: SafetyModerationReportProps,
) {
  const matches = (): HarmfulContentMatch[] => props.matches ?? [];
  const groupedMatches = createMemo(() => groupMatches(matches()));
  const grouped = createMemo(() => {
    const groups: Array<{
      source: HarmfulContentSource;
      label: string;
      matches: SafetyMatchGroup[];
    }> = [];
    for (const source of ["openai", "gcp"] as const) {
      const sourceMatches = groupedMatches().filter(
        (group) => group.parent.source === source,
      );
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
    <div data-testid="report-safety__moderation" class="relative space-y-2 pb-8 pr-8">
      <p class="text-[11px] text-muted-foreground">
        <span data-testid="safety-count">{groupedMatches().length} flagged</span>
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
                    {(matchGroup) => (
                      <li data-testid="safety-match-group" data-key={matchGroup.key}>
                        <MatchCard
                          match={matchGroup.parent}
                          onUtteranceClick={props.onUtteranceClick}
                          canJumpToUtterance={props.canJumpToUtterance}
                        />
                        <Show when={matchGroup.chunkMatches.length > 0}>
                          <details data-testid="safety-chunk-details" class="mt-1.5">
                            <summary class="cursor-pointer text-[11px] text-muted-foreground">
                              {matchGroup.chunkMatches.length} chunk
                              {matchGroup.chunkMatches.length === 1 ? "" : "s"}
                            </summary>
                            <div class="mt-1.5 space-y-1.5">
                              <For each={matchGroup.chunkMatches}>
                                {(chunkMatch) => (
                                  <MatchCard
                                    match={chunkMatch}
                                    onUtteranceClick={props.onUtteranceClick}
                                    canJumpToUtterance={props.canJumpToUtterance}
                                    child
                                  />
                                )}
                              </For>
                            </div>
                          </details>
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
      <FeedbackBell bell_location="card:safety-moderation" />
    </div>
  );
}
