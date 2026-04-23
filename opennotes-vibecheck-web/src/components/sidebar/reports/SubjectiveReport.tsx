import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

export interface SubjectiveReportProps {
  claims: SubjectiveClaim[];
}

export default function SubjectiveReport(props: SubjectiveReportProps) {
  const claims = (): SubjectiveClaim[] => props.claims ?? [];

  return (
    <div
      data-testid="report-opinions_sentiments__subjective"
      class="space-y-2"
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
                class="text-xs text-foreground"
              >
                <span class="mr-1 inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {claim.stance}
                </span>
                {claim.claim_text}
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
