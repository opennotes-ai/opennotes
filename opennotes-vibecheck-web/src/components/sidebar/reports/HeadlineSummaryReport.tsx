import { Show, type JSX } from "solid-js";
import type { ResolvedHeadline } from "~/lib/headline-fallback";

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
          class="max-w-prose space-y-1"
        >
          <p
            data-testid="headline-summary-text"
            class="text-base leading-7 text-foreground"
          >
            {h().text}
          </p>
        </section>
      )}
    </Show>
  );
}
