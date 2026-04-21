import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import { formatDate, humanizeLabel, cn } from "@opennotes/ui/utils";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import IdBadge from "~/components/ui/id-badge";
import { getHelpfulnessTooltip, TERM_DESCRIPTIONS } from "@opennotes/ui/palettes";
import NoteFilter, { type NoteFilterValues } from "~/components/ui/note-filter";
import { ToggleGroup, ToggleGroupItem } from "~/components/ui/toggle-group";
import EmptyState from "~/components/ui/empty-state";
import { ClipboardList } from "~/components/ui/icons";

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

type SortMode = "count" | "disagreement" | "has_score";

type RequestGroup = {
  requestId: string;
  sourceUrl: string | null;
  sourceTitle: string | null;
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
    const sourceTitle = noteWithSource
      ? (noteWithSource.attributes.message_metadata as { title?: string }).title ?? null
      : null;
    return { requestId, sourceUrl, sourceTitle, notes: grouped, noteCount: total, disagreementScore };
  });
}

export default function NoteDetails(props: {
  notes: DetailedNoteResource[];
  currentTier: string;
  sortBy: SortMode;
  onSortChange: (mode: SortMode) => void;
  filterClassification: string[];
  filterStatus: string[];
  onFilterChange: (values: NoteFilterValues) => void;
}) {
  const groups = createMemo(() => groupByRequest(props.notes));

  const sortedGroups = createMemo(() => {
    const g = [...groups()];
    const mode = props.sortBy;
    if (mode === "count") {
      g.sort((a, b) => b.noteCount - a.noteCount);
    } else if (mode === "disagreement") {
      g.sort((a, b) => b.disagreementScore - a.disagreementScore);
    } else if (mode === "has_score") {
      g.sort((a, b) => {
        const aHasScore = a.notes.some((n) => n.attributes.status !== "NEEDS_MORE_RATINGS") ? 1 : 0;
        const bHasScore = b.notes.some((n) => n.attributes.status !== "NEEDS_MORE_RATINGS") ? 1 : 0;
        return bHasScore - aHasScore;
      });
    }
    return g;
  });

  return (
    <section>
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 id="per-note-breakdown" class="text-xl font-semibold">Per-Note Breakdown</h2>
          <p class="mt-1 text-sm text-muted-foreground">Each note examined — who wrote it, how it was rated, and whether consensus emerged</p>
        </div>
        <Show when={props.notes.length > 1 || props.filterClassification.length > 0 || props.filterStatus.length > 0}>
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-muted-foreground">Sort by:</span>
            <ToggleGroup
              value={props.sortBy}
              onChange={(value) => { if (value) props.onSortChange(value as SortMode); }}
              class="rounded-md border border-input"
              size="sm"
            >
              <ToggleGroupItem value="count" data-testid="sort-count" class="px-3 py-1.5 text-xs font-medium">
                Note Count
              </ToggleGroupItem>
              <ToggleGroupItem value="disagreement" data-testid="sort-disagreement" class="px-3 py-1.5 text-xs font-medium">
                Disagreement
              </ToggleGroupItem>
              <ToggleGroupItem value="has_score" data-testid="sort-has-score" class="px-3 py-1.5 text-xs font-medium">
                Has Score
              </ToggleGroupItem>
            </ToggleGroup>
            <NoteFilter
              classification={props.filterClassification}
              status={props.filterStatus}
              onChange={props.onFilterChange}
            />
          </div>
        </Show>
      </div>

      <Show
        when={props.notes.length > 0}
        fallback={
          <EmptyState
            icon={<ClipboardList class="size-6" />}
            message="No notes available"
            description="Notes appear once agents begin writing and rating."
          />
        }
      >
        <div class="space-y-3">
          <For each={sortedGroups()}>
            {(group) => (
              <details id={`request-${group.requestId}`} class="rounded-lg border border-border" open>
                <summary class="flex cursor-pointer items-center justify-between gap-2 rounded-t-lg p-3 hover:bg-muted/50">
                  <span class="min-w-0 text-sm font-medium">
                    {group.sourceTitle
                      ? <>Notes responding to: {group.sourceTitle}</>
                      : <>
                          Request{" "}
                          <IdBadge idValue={group.requestId} variant="muted" />
                        </>}
                    <Show when={group.sourceUrl}>
                      {(url) => {
                        const isSafe = () => /^https?:\/\//i.test(url());
                        return (
                          <Show
                            when={isSafe()}
                            fallback={
                              <span class="ml-2 text-xs text-muted-foreground">{url()}</span>
                            }
                          >
                            <a
                              href={url()}
                              target="_blank"
                              rel="noopener noreferrer"
                              class="ml-2 text-xs text-primary hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              Read what they're annotating ↗
                            </a>
                          </Show>
                        );
                      }}
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
                        <div id={`note-${note.attributes.note_id}`} class="rounded-lg border border-border bg-card p-4" data-testid="note-card">
                          <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
                            <div class="min-w-0 flex-1" data-testid="note-summary">
                              <div class="font-normal leading-snug">{attrs.summary}</div>
                              <div class="mt-0.5 text-xs text-muted-foreground">
                                Note{" "}
                                <IdBadge idValue={attrs.note_id} variant="muted" class="mx-1" />
                                by {attrs.author_agent_name}
                              </div>
                            </div>
                            <div class="flex items-center gap-1.5" data-testid="note-badges">
                              <Badge variant={CLASSIFICATION_VARIANT[attrs.classification] ?? "indigo"} title={TERM_DESCRIPTIONS[attrs.classification]}>
                                {humanizeLabel(attrs.classification)}
                              </Badge>
                              <Badge variant={STATUS_VARIANT[attrs.status] ?? "muted"} title={TERM_DESCRIPTIONS[attrs.status]}>
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
                            <Show when={attrs.ratings && attrs.ratings.length > 0}>
                              <span class="flex items-center gap-1">
                                <For each={Object.entries(
                                  (attrs.ratings ?? []).reduce<Record<string, number>>((acc, r) => {
                                    acc[r.helpfulness_level] = (acc[r.helpfulness_level] || 0) + 1;
                                    return acc;
                                  }, {})
                                )}>
                                  {([level, count]) => (
                                    <Badge variant={HELPFULNESS_VARIANT[level] ?? "muted"} class="text-xs" title={TERM_DESCRIPTIONS[level]}>
                                      {humanizeLabel(level)}: {count}
                                    </Badge>
                                  )}
                                </For>
                              </span>
                            </Show>
                            <span>Created: {formatDate(attrs.created_at)}</span>
                          </div>

                          <Show when={attrs.ratings && attrs.ratings.length > 0}>
                            <details class="mt-3 border-t border-border pt-3">
                              <summary class="cursor-pointer text-xs font-semibold text-muted-foreground">
                                Ratings ({attrs.ratings!.length})
                              </summary>
                              <div class="mt-1.5 flex flex-wrap gap-1.5">
                                <For each={attrs.ratings}>
                                  {(rating) => (
                                    <Badge variant={HELPFULNESS_VARIANT[rating.helpfulness_level] ?? "muted"} title={TERM_DESCRIPTIONS[rating.helpfulness_level]}>
                                      {rating.rater_agent_name}: {humanizeLabel(rating.helpfulness_level)}
                                    </Badge>
                                  )}
                                </For>
                              </div>
                            </details>
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
