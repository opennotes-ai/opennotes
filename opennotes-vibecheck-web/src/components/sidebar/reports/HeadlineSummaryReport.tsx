import { Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";

type HeadlineSummary = components["schemas"]["HeadlineSummary"];

export interface HeadlineSummaryReportProps {
  headline: HeadlineSummary | null;
}

export default function HeadlineSummaryReport(
  props: HeadlineSummaryReportProps,
): JSX.Element {
  return (
    <Show when={props.headline} fallback={null}>
      {(h) => (
        <section
          data-testid="headline-summary"
          class="rounded-md border border-border bg-background/60 p-3"
        >
          <p
            data-testid="headline-summary-text"
            class="text-sm leading-relaxed text-foreground"
          >
            {h().text}
          </p>
        </section>
      )}
    </Show>
  );
}
