import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import UtteranceRef from "../UtteranceRef";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

export interface SubjectiveReportProps {
  claims: SubjectiveClaim[];
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
}

/** @deprecated Kept only for HighlightsReport's legacy subjective_claims fallback; remove once legacy data is no longer expected. */
export default function SubjectiveReport(props: SubjectiveReportProps) {
  const claims = (): SubjectiveClaim[] => props.claims ?? [];

  return (
    <div
      data-testid="report-opinions_sentiments__subjective"
      class="relative space-y-2 pb-8 pr-8"
    >
      <p class="text-[11px] text-muted-foreground">
        {claims().length} claim{claims().length === 1 ? "" : "s"}
      </p>
      <Show
        when={claims().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No subjective claims detected.
          </p>
        }
      >
        <ul class="space-y-1">
          <For each={claims()}>
            {(claim) => (
              <li
                data-testid="subjective-claim"
                class="flex items-start gap-2 text-xs text-foreground"
              >
                <span class="shrink-0 inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {claim.stance}
                </span>
                <div class="min-w-0 flex-1">
                  <ExpandableText
                    text={claim.claim_text}
                    lines={2}
                    testId="subjective-claim-text"
                    class="text-foreground"
                  />
                </div>
                <Show when={claim.utterance_id}>
                  {(utteranceId) => (
                    <UtteranceRef
                      utteranceId={String(utteranceId())}
                      label={`turn ${utteranceId()}`}
                      onClick={props.onUtteranceClick ?? (() => undefined)}
                      disabled={
                        !props.canJumpToUtterance || !props.onUtteranceClick
                      }
                      testId="subjective-claim-utterance-ref"
                      class="mt-0.5 shrink-0"
                    />
                  )}
                </Show>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <FeedbackBell bell_location="card:subjective" />
    </div>
  );
}
