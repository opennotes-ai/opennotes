import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import { categoryColor, categoryColorClasses } from "~/lib/category-colors";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type ImageModerationMatch = components["schemas"]["ImageModerationMatch"];

const SAFESEARCH_FIELDS = [
  "adult",
  "violence",
  "racy",
  "medical",
  "spoof",
] as const;
type SafeSearchField = (typeof SAFESEARCH_FIELDS)[number];
const FLAGGED_CATEGORY_DISPLAY_THRESHOLD = 0.5;

export interface ImageModerationReportProps {
  matches: ImageModerationMatch[];
}

function flaggedCategories(match: ImageModerationMatch): SafeSearchField[] {
  if (match.flagged) {
    return SAFESEARCH_FIELDS.filter(
      (field) => match[field] > FLAGGED_CATEGORY_DISPLAY_THRESHOLD,
    );
  }
  return SAFESEARCH_FIELDS.filter((field) => match[field] >= 0.75);
}

function ImageMatchCard(props: { match: ImageModerationMatch }): JSX.Element {
  const categories = () => flaggedCategories(props.match);

  return (
    <li
      data-testid="image-moderation-match"
      data-flagged={props.match.flagged ? "true" : "false"}
      class={
        props.match.flagged
          ? "overflow-hidden rounded-md border border-destructive/40 bg-background text-xs"
          : "overflow-hidden rounded-md border border-border bg-background text-xs"
      }
    >
      <div class="aspect-video w-full bg-muted">
        <img
          src={props.match.image_url}
          alt=""
          loading="lazy"
          class="h-full w-full object-cover"
        />
      </div>
      <div class="space-y-2 p-2">
        <div class="flex items-center gap-2">
          <span
            class={
              props.match.flagged
                ? "inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                : "inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
            }
          >
            {props.match.flagged ? "flagged" : "clear"}
          </span>
        </div>
        <Show when={categories().length > 0}>
          <div class="flex flex-wrap gap-1">
            <For each={categories()}>
              {(category) => {
                const color = categoryColor(category, props.match[category]);
                return (
                  <span
                    data-testid="image-moderation-category"
                    data-color={color}
                    class={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${categoryColorClasses(color)}`}
                  >
                    {category}
                  </span>
                );
              }}
            </For>
          </div>
        </Show>
      </div>
    </li>
  );
}

export default function ImageModerationReport(
  props: ImageModerationReportProps,
): JSX.Element {
  const matches = (): ImageModerationMatch[] => props.matches ?? [];
  const flaggedMatches = () => matches().filter((match) => match.flagged);
  const clearMatches = () => matches().filter((match) => !match.flagged);
  const clearSummary = () =>
    `${clearMatches().length} clear image${clearMatches().length === 1 ? "" : "s"}`;

  return (
    <div data-testid="report-safety__image_moderation" class="relative space-y-2">
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
        <div class="space-y-2">
          <Show when={flaggedMatches().length > 0}>
            <ul
              data-testid="image-moderation-flagged-list"
              class="grid grid-cols-1 gap-2 sm:grid-cols-2"
            >
              <For each={flaggedMatches()}>
                {(match) => <ImageMatchCard match={match} />}
              </For>
            </ul>
          </Show>
          <Show when={clearMatches().length > 0}>
            <details
              data-testid="image-moderation-clear-group"
              class="rounded-md border border-border bg-muted/30 px-2 py-1.5"
            >
              <summary class="cursor-pointer text-xs font-medium text-muted-foreground">
                {clearSummary()}
              </summary>
              <p class="mt-2 text-[11px] text-muted-foreground">
                No SafeSearch categories crossed the threshold.
              </p>
              <ul class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                <For each={clearMatches()}>
                  {(match) => <ImageMatchCard match={match} />}
                </For>
              </ul>
            </details>
          </Show>
        </div>
      </Show>
      <FeedbackBell bell_location="card:image-moderation" />
    </div>
  );
}
