import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import { categoryColor, categoryColorClasses } from "~/lib/category-colors";

type FrameFinding = components["schemas"]["FrameFinding"];
type VideoModerationMatch = components["schemas"]["VideoModerationMatch"];

const SAFESEARCH_FIELDS = [
  "adult",
  "violence",
  "racy",
  "medical",
  "spoof",
] as const;
type SafeSearchField = (typeof SAFESEARCH_FIELDS)[number];
const FLAGGED_CATEGORY_DISPLAY_THRESHOLD = 0.5;

export interface VideoModerationReportProps {
  matches: VideoModerationMatch[];
}

function formatOffset(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0.0s";
  return `${(ms / 1000).toFixed(1)}s`;
}

function flaggedCategories(frame: FrameFinding): SafeSearchField[] {
  if (frame.flagged) {
    return SAFESEARCH_FIELDS.filter(
      (field) => frame[field] > FLAGGED_CATEGORY_DISPLAY_THRESHOLD,
    );
  }
  return SAFESEARCH_FIELDS.filter((field) => frame[field] >= 0.75);
}

export default function VideoModerationReport(
  props: VideoModerationReportProps,
): JSX.Element {
  const matches = (): VideoModerationMatch[] => props.matches ?? [];

  return (
    <div data-testid="report-safety__video_moderation" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        {matches().length} video{matches().length === 1 ? "" : "s"} checked
      </p>
      <Show
        when={matches().length > 0}
        fallback={
          <p data-testid="video-moderation-empty" class="text-xs text-muted-foreground">
            No video safety matches.
          </p>
        }
      >
        <ul class="space-y-2">
          <For each={matches()}>
            {(match) => (
              <li
                data-testid="video-moderation-match"
                data-flagged={match.flagged ? "true" : "false"}
                class={
                  match.flagged
                    ? "rounded-md border border-destructive/40 bg-background p-3 text-xs"
                    : "rounded-md border border-border bg-background p-3 text-xs"
                }
              >
                <div class="flex items-start gap-2">
                  <p class="min-w-0 break-all font-medium text-foreground">
                    {match.video_url}
                  </p>
                </div>
                <Show
                  when={match.frame_findings.length > 0}
                  fallback={
                    <p class="mt-2 text-[11px] text-muted-foreground">
                      No sampled frames returned.
                    </p>
                  }
                >
                  <ul class="mt-2 grid grid-cols-1 gap-1.5">
                    <For each={match.frame_findings}>
                      {(frame) => (
                        <li
                          data-testid="video-frame-finding"
                          data-flagged={frame.flagged ? "true" : "false"}
                          class="rounded-md bg-muted/60 p-2"
                        >
                          <div class="flex items-center justify-between gap-2">
                            <span class="font-mono text-[11px] text-foreground">
                              {formatOffset(frame.frame_offset_ms)}
                            </span>
                            <span
                              data-testid="video-frame-flag"
                              class={
                                frame.flagged
                                  ? "inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                                  : "inline-flex items-center rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
                              }
                            >
                              {frame.flagged ? "flagged" : "clear"}
                            </span>
                          </div>
                          <Show when={flaggedCategories(frame).length > 0}>
                            <div class="mt-1.5 flex flex-wrap gap-1">
                              <For each={flaggedCategories(frame)}>
                                {(category) => {
                                  const color = categoryColor(
                                    category,
                                    frame[category],
                                  );
                                  return (
                                    <span
                                      data-testid="video-frame-category"
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
                        </li>
                      )}
                    </For>
                  </ul>
                </Show>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
