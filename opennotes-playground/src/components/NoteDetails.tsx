import { For, Show, createSignal, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import { formatDate, humanizeLabel, truncateId } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import { getHelpfulnessTooltip } from "~/lib/scoring-tiers";
import { cn } from "~/lib/cn";

type DetailedNoteResource = components["schemas"]["DetailedNoteResource"];

const CLASSIFICATION_VARIANT: Record<string, BadgeVariant> = {
  NOT_MISLEADING: "indigo",
  MISINFORMED_OR_POTENTIALLY_MISLEADING: "danger",
};

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  CURRENTLY_RATED_HELPFUL: "success",
  CURRENTLY_RATED_NOT_HELPFUL: "danger",
  NEEDS_MORE_RATINGS: "warning",
};

const HELPFULNESS_VARIANT: Record<string, BadgeVariant> = {
  HELPFUL: "success",
  SOMEWHAT_HELPFUL: "warning",
  NOT_HELPFUL: "danger",
};

type SortMode = "count" | "disagreement";

type RequestGroup = {
  requestId: string;
  sourceUrl: string | null;
  notes: DetailedNoteResource[];
  noteCount: number;
  disagreementScore: number;
};

function groupByRequest(notes: DetailedNoteResource[]): RequestGroup[] {
  const groups = new Map<string, DetailedNoteResource[]>();
  for (const note of notes) {
    const rid = note.attributes.request_id ?? "ungrouped";
    if (!groups.has(rid)) groups.set(rid, []);
    groups.get(rid)!.push(note);
  }
  return Array.from(groups.entries()).map(([requestId, grouped]) => {
    const misleading = grouped.filter(
      (n) => n.attributes.classification === "MISINFORMED_OR_POTENTIALLY_MISLEADING",
    ).length;
    const total = grouped.length;
    const ratio = total > 0 ? misleading / total : 0;
    const disagreementScore = 1 - Math.abs(2 * ratio - 1);
    const noteWithSource = grouped.find((n) => {
      const m = n.attributes.message_metadata;
      return m && typeof m === "object" && "source_url" in m && typeof m.source_url === "string";
    });
    const sourceUrl = noteWithSource
      ? (noteWithSource.attributes.message_metadata as { source_url: string }).source_url
      : null;
    return { requestId, sourceUrl, notes: grouped, noteCount: total, disagreementScore };
  });
}

export default function NoteDetails(props: { notes: DetailedNoteResource[]; currentTier: string }) {
  const [sortBy, setSortBy] = createSignal<SortMode>("count");

  const groups = createMemo(() => groupByRequest(props.notes));

  const sortedGroups = createMemo(() => {
    const g = [...groups()];
    const mode = sortBy();
    if (mode === "count") {
      g.sort((a, b) => b.noteCount - a.noteCount);
    } else {
      g.sort((a, b) => b.disagreementScore - a.disagreementScore);
    }
    return g;
  });

  return (
    <section>
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-xl font-semibold">Per-Note Breakdown</h2>
        <Show when={props.notes.length > 1}>
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-muted-foreground">Sort by:</span>
            <div class="flex overflow-hidden rounded-md border border-input">
              <button
                class={cn(
                  "px-3 py-1.5 text-xs font-medium transition-colors",
                  sortBy() === "count" ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
                aria-pressed={sortBy() === "count"}
                onClick={() => setSortBy("count")}
              >
                Note Count
              </button>
              <button
                class={cn(
                  "border-l border-input px-3 py-1.5 text-xs font-medium transition-colors",
                  sortBy() === "disagreement" ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                )}
                aria-pressed={sortBy() === "disagreement"}
                onClick={() => setSortBy("disagreement")}
              >
                Disagreement
              </button>
            </div>
          </div>
        </Show>
      </div>

      <Show
        when={props.notes.length > 0}
        fallback={<p class="text-muted-foreground">No notes available.</p>}
      >
        <div class="space-y-3">
          <For each={sortedGroups()}>
            {(group) => (
              <details class="rounded-lg border border-border" open>
                <summary class="flex cursor-pointer items-center justify-between gap-2 rounded-t-lg p-3 hover:bg-muted/50">
                  <span class="min-w-0 text-sm font-medium">
                    Request {truncateId(group.requestId)}
                    <Show when={group.sourceUrl}>
                      {(url) => (
                        <a
                          href={url()}
                          target="_blank"
                          rel="noopener noreferrer"
                          class="ml-2 text-xs text-primary hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Source ↗
                        </a>
                      )}
                    </Show>
                  </span>
                  <span class="shrink-0 text-xs text-muted-foreground">
                    {group.noteCount} note{group.noteCount !== 1 ? "s" : ""}
                    <Show when={group.disagreementScore > 0}>
                      {` · ${(group.disagreementScore * 100).toFixed(0)}% disagreement`}
                    </Show>
                  </span>
                </summary>
                <div class="space-y-2 p-3 pt-0">
                  <For each={group.notes}>
                    {(note) => {
                      const attrs = note.attributes;
                      return (
                        <div class="rounded-lg border border-border bg-card p-4">
                          <div class="flex flex-wrap items-start justify-between gap-2">
                            <div class="min-w-0 flex-1">
                              <div class="font-medium leading-snug">{attrs.summary}</div>
                              <div class="mt-0.5 text-xs text-muted-foreground">
                                Note {truncateId(attrs.note_id)} by {attrs.author_agent_name}
                              </div>
                            </div>
                            <div class="flex shrink-0 items-center gap-1.5">
                              <Badge variant={CLASSIFICATION_VARIANT[attrs.classification] ?? "indigo"}>
                                {humanizeLabel(attrs.classification)}
                              </Badge>
                              <Badge variant={STATUS_VARIANT[attrs.status] ?? "muted"}>
                                {humanizeLabel(attrs.status)}
                              </Badge>
                            </div>
                          </div>

                          <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                            <span
                              tabindex="0"
                              title={getHelpfulnessTooltip(attrs.helpfulness_score, props.currentTier)}
                              aria-label={getHelpfulnessTooltip(attrs.helpfulness_score, props.currentTier)}
                            >
                              Helpfulness: <strong class="text-foreground">{attrs.helpfulness_score?.toFixed(2) ?? "N/A"}</strong>
                            </span>
                            <span>Created: {formatDate(attrs.created_at)}</span>
                          </div>

                          <Show when={attrs.ratings && attrs.ratings.length > 0}>
                            <div class="mt-3 border-t border-border pt-3">
                              <div class="mb-1.5 text-xs font-semibold text-muted-foreground">
                                Ratings ({attrs.ratings!.length})
                              </div>
                              <div class="flex flex-wrap gap-1.5">
                                <For each={attrs.ratings}>
                                  {(rating) => (
                                    <Badge variant={HELPFULNESS_VARIANT[rating.helpfulness_level] ?? "muted"}>
                                      {rating.rater_agent_name}: {humanizeLabel(rating.helpfulness_level)}
                                    </Badge>
                                  )}
                                </For>
                              </div>
                            </div>
                          </Show>
                        </div>
                      );
                    }}
                  </For>
                </div>
              </details>
            )}
          </For>
        </div>
      </Show>
    </section>
  );
}
