import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";

type ImageModerationMatch = components["schemas"]["ImageModerationMatch"];

const SAFESEARCH_FIELDS = [
  "adult",
  "violence",
  "racy",
  "medical",
  "spoof",
] as const;

export interface ImageModerationReportProps {
  matches: ImageModerationMatch[];
}

function flaggedCategories(match: ImageModerationMatch): string[] {
  return SAFESEARCH_FIELDS.filter((field) => match[field] >= 0.75);
}

export default function ImageModerationReport(
  props: ImageModerationReportProps,
): JSX.Element {
  const matches = (): ImageModerationMatch[] => props.matches ?? [];

  return (
    <div data-testid="report-safety__image_moderation" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        {matches().length} image{matches().length === 1 ? "" : "s"} checked
      </p>
      <Show
        when={matches().length > 0}
        fallback={
          <p data-testid="image-moderation-empty" class="text-xs text-muted-foreground">
            No image safety matches.
          </p>
        }
      >
        <ul class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <For each={matches()}>
            {(match) => (
              <li
                data-testid="image-moderation-match"
                data-flagged={match.flagged ? "true" : "false"}
                class={
                  match.flagged
                    ? "overflow-hidden rounded-md border border-destructive/40 bg-background text-xs"
                    : "overflow-hidden rounded-md border border-border bg-background text-xs"
                }
              >
                <div class="aspect-video w-full bg-muted">
                  <img
                    src={match.image_url}
                    alt=""
                    loading="lazy"
                    class="h-full w-full object-cover"
                  />
                </div>
                <div class="space-y-2 p-2">
                  <div class="flex items-center gap-2">
                    <span
                      class={
                        match.flagged
                          ? "inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                          : "inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
                      }
                    >
                      {match.flagged ? "flagged" : "clear"}
                    </span>
                  </div>
                  <Show
                    when={flaggedCategories(match).length > 0}
                    fallback={
                      <p class="text-[11px] text-muted-foreground">
                        No SafeSearch categories crossed the threshold.
                      </p>
                    }
                  >
                    <div class="flex flex-wrap gap-1">
                      <For each={flaggedCategories(match)}>
                        {(category) => (
                          <span
                            data-testid="image-moderation-category"
                            class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                          >
                            {category}
                          </span>
                        )}
                      </For>
                    </div>
                  </Show>
                </div>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
