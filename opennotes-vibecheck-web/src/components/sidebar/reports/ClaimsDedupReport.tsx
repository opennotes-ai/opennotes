import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";

type ClaimsReport = components["schemas"]["ClaimsReport"];
type DedupedClaim = components["schemas"]["DedupedClaim"];

export interface ClaimsDedupReportProps {
  claimsReport: ClaimsReport;
}

export default function ClaimsDedupReport(props: ClaimsDedupReportProps) {
  const claims = (): DedupedClaim[] =>
    props.claimsReport?.deduped_claims ?? [];

  const sorted = createMemo(() =>
    [...claims()].sort(
      (a, b) => (b.occurrence_count ?? 0) - (a.occurrence_count ?? 0),
    ),
  );

  return (
    <div data-testid="report-facts_claims__dedup" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        {sorted().length} claim{sorted().length === 1 ? "" : "s"}
      </p>
      <Show
        when={sorted().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No repeated claims identified.
          </p>
        }
      >
        <ul data-testid="deduped-claims-list" class="space-y-1.5">
          <For each={sorted()}>
            {(claim) => (
              <li data-testid="deduped-claim-item" class="text-xs">
                <ExpandableText
                  text={claim.canonical_text}
                  lines={2}
                  testId="deduped-claim-text"
                  class="text-foreground"
                />
                <p class="mt-0.5 text-[11px] text-muted-foreground">
                  <span data-testid="deduped-claim-occurrences">
                    &times;{claim.occurrence_count}
                  </span>
                  <span class="mx-1">&middot;</span>
                  <span>
                    {claim.author_count} author
                    {claim.author_count === 1 ? "" : "s"}
                  </span>
                </p>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
