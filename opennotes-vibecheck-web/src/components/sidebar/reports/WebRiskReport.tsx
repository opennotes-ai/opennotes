import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type WebRiskFinding = components["schemas"]["WebRiskFinding"];

export interface WebRiskReportProps {
  findings: WebRiskFinding[];
}

function threatLabel(threat: WebRiskFinding["threat_types"][number]): string {
  return threat.replaceAll("_", " ").toLowerCase();
}

export default function WebRiskReport(
  props: WebRiskReportProps,
): JSX.Element {
  const findings = (): WebRiskFinding[] => props.findings ?? [];

  return (
    <div data-testid="report-safety__web_risk" class="relative space-y-2 pb-8 pr-8">
      <p class="text-[11px] text-muted-foreground">
        {findings().length} flagged URL{findings().length === 1 ? "" : "s"}
      </p>
      <Show
        when={findings().length > 0}
        fallback={
          <p data-testid="web-risk-empty" class="text-xs text-muted-foreground">
            No Web Risk findings.
          </p>
        }
      >
        <ul class="space-y-2">
          <For each={findings()}>
            {(finding) => (
              <li
                data-testid="web-risk-finding"
                class="rounded-md border border-border bg-background p-3 text-xs"
              >
                <p class="break-all font-medium text-foreground">
                  {finding.url}
                </p>
                <div class="mt-2 flex flex-wrap gap-1">
                  <For each={finding.threat_types}>
                    {(threat) => (
                      <span
                        data-testid="web-risk-threat"
                        class="inline-flex items-center rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive"
                      >
                        {threatLabel(threat)}
                      </span>
                    )}
                  </For>
                </div>
              </li>
            )}
          </For>
        </ul>
      </Show>
      <FeedbackBell bell_location="card:web-risk" />
    </div>
  );
}
