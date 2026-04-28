import { For, Show, createMemo, createSignal } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";

type ClaimsReport = components["schemas"]["ClaimsReport"];
type DedupedClaim = components["schemas"]["DedupedClaim"];

export interface ClaimsDedupReportProps {
  claimsReport: ClaimsReport;
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
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
            {(claim) => {
              const [isOpen, setIsOpen] = createSignal(false);
              const utteranceIds = () => claim.utterance_ids ?? [];
              const primaryId = () => utteranceIds()[0];
              const remainingIds = () => utteranceIds().slice(1);
              const disabled = () =>
                !props.canJumpToUtterance || !props.onUtteranceClick;
              return (
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
                  <Show when={primaryId()}>
                    {(id) => (
                      <div
                        data-testid="deduped-claim-utterance-refs"
                        class="relative mt-1 flex flex-wrap items-center gap-1"
                      >
                        <UtteranceRef
                          utteranceId={String(id())}
                          label={`turn ${id()}`}
                          onClick={props.onUtteranceClick ?? (() => undefined)}
                          disabled={disabled()}
                          testId="deduped-claim-utterance-ref"
                        />
                        <Show when={remainingIds().length > 0}>
                          <button
                            type="button"
                            data-testid="deduped-claim-more-utterances"
                            class="inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                            aria-expanded={isOpen() ? "true" : "false"}
                            onClick={() => setIsOpen((open) => !open)}
                            onKeyDown={(event) => {
                              if (event.key === "Escape") {
                                setIsOpen(false);
                              }
                            }}
                          >
                            +{remainingIds().length} more
                          </button>
                          <Show when={isOpen()}>
                            <div
                              data-testid="deduped-claim-utterance-popover"
                              class="absolute left-0 top-full z-10 mt-1 flex flex-wrap gap-1 rounded-md border border-border bg-popover p-2 shadow-md"
                              onKeyDown={(event) => {
                                if (event.key === "Escape") setIsOpen(false);
                              }}
                            >
                              <For each={remainingIds()}>
                                {(remainingId) => (
                                  <UtteranceRef
                                    utteranceId={String(remainingId)}
                                    label={`turn ${remainingId}`}
                                    onClick={props.onUtteranceClick ?? (() => undefined)}
                                    disabled={disabled()}
                                    testId="deduped-claim-popover-utterance-ref"
                                  />
                                )}
                              </For>
                            </div>
                          </Show>
                        </Show>
                      </div>
                    )}
                  </Show>
                </li>
              );
            }}
          </For>
        </ul>
      </Show>
    </div>
  );
}
