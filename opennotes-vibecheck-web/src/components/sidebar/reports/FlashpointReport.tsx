import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type FlashpointMatch = components["schemas"]["FlashpointMatch"];

export interface FlashpointReportProps {
  matches: FlashpointMatch[];
}

export default function FlashpointReport(props: FlashpointReportProps) {
  const matches = (): FlashpointMatch[] => props.matches ?? [];

  return (
    <div data-testid="report-tone_dynamics__flashpoint" class="space-y-2">
      <p class="text-[11px] text-muted-foreground">
        {matches().length} moment{matches().length === 1 ? "" : "s"}
      </p>
      <Show
        when={matches().length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No flashpoint moments detected.
          </p>
        }
      >
        <ul class="space-y-1.5">
          <For each={matches()}>
            {(match) => (
              <li class="text-xs">
                <div class="flex items-center gap-2">
                  <span
                    data-testid="flashpoint-risk-level"
                    class="inline-flex items-center rounded-full bg-chart-3/15 px-1.5 py-0.5 text-[10px] font-medium text-foreground"
                  >
                    {match.risk_level}
                  </span>
                  <span class="font-mono text-[10px] text-muted-foreground">
                    {match.derailment_score}/100
                  </span>
                </div>
                <p class="mt-1 line-clamp-2 text-foreground">
                  {match.reasoning}
                </p>
                <p class="mt-0.5 font-mono text-[10px] text-muted-foreground">
                  utterance {match.utterance_id}
                </p>
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
