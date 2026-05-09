import { Show, type JSX } from "solid-js";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import { FeedbackBell } from "../../feedback/FeedbackBell";

export interface HeadlineSummaryReportProps {
  headline: ResolvedHeadline | null;
}

export default function HeadlineSummaryReport(
  props: HeadlineSummaryReportProps,
): JSX.Element {
  return (
    <Show when={props.headline} fallback={null}>
      {(h) => (
        <section
          data-testid="headline-summary"
          data-headline-kind={h().kind}
          data-headline-source={h().source}
          class="relative w-full space-y-1 pb-8 pr-8"
        >
          <p
            data-testid="headline-summary-text"
            class="text-base leading-7 text-foreground"
          >
            {h().text}
          </p>
          <FeedbackBell bell_location="card:headline-summary" />
        </section>
      )}
    </Show>
  );
}
