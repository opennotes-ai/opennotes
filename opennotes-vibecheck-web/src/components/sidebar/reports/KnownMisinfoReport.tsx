import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type FactCheckMatch = components["schemas"]["FactCheckMatch"];

export interface KnownMisinfoReportProps {
  matches: FactCheckMatch[];
}

export default function KnownMisinfoReport(props: KnownMisinfoReportProps) {
  const items = (): FactCheckMatch[] => props.matches ?? [];

  const grouped = createMemo(() => {
    const map = new Map<string, FactCheckMatch[]>();
    for (const item of items()) {
      const list = map.get(item.claim_text);
      if (list) list.push(item);
      else map.set(item.claim_text, [item]);
    }
    return Array.from(map.entries());
  });

  return (
    <div data-testid="report-facts_claims__known_misinfo" class="relative space-y-2 pb-8 pr-8">
      <p class="text-[11px] text-muted-foreground">
        {grouped().length} claim{grouped().length === 1 ? "" : "s"}
      </p>
      <Show
        when={grouped().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No known-misinformation matches.
          </p>
        }
      >
        <ul class="space-y-2">
          <For each={grouped()}>
            {([claimText, reviews]) => (
              <li
                data-testid="known-misinfo-item"
                class="rounded-md border border-border bg-background p-2 text-xs"
              >
                <ExpandableText
                  text={claimText}
                  lines={2}
                  testId="known-misinfo-claim-text"
                  class="text-foreground"
                />
                <ul class="mt-1.5 space-y-1">
                  <For each={reviews}>
                    {(review) => (
                      <li class="flex items-center justify-between gap-2">
                        <div class="min-w-0 flex-1">
                          <span class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[10px] font-medium text-destructive">
                            {review.textual_rating}
                          </span>
                          <span class="ml-2 truncate text-[11px] text-muted-foreground">
                            {review.publisher}
                          </span>
                        </div>
                        <a
                          href={review.review_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          class="shrink-0 text-[11px] text-primary underline-offset-2 hover:underline"
                        >
                          fact check
                        </a>
                      </li>
                    )}
                  </For>
                </ul>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <FeedbackBell bell_location="card:known-misinfo" />
    </div>
  );
}
