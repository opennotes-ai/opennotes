import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import { formatDate, humanizeLabel, truncateId } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import { getHelpfulnessTooltip } from "~/lib/scoring-tiers";

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

export default function NoteDetails(props: { notes: DetailedNoteResource[]; currentTier: string }) {
  return (
    <section>
      <h2 class="mb-4 text-xl font-semibold">Per-Note Breakdown</h2>
      <Show
        when={props.notes.length > 0}
        fallback={<p class="text-muted-foreground">No notes available.</p>}
      >
        <div class="space-y-3">
          <For each={props.notes}>
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
                      title={getHelpfulnessTooltip(attrs.helpfulness_score, props.currentTier)}
                      aria-label={getHelpfulnessTooltip(attrs.helpfulness_score, props.currentTier)}
                    >
                      Helpfulness: <strong class="text-foreground">{attrs.helpfulness_score.toFixed(2)}</strong>
                    </span>
                    <Show when={attrs.request_id}>
                      <span>Request: {truncateId(attrs.request_id)}</span>
                    </Show>
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
      </Show>
    </section>
  );
}
