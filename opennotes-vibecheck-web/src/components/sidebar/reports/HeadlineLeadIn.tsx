import { Show, type JSX } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import type { components } from "~/lib/generated-types";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import HeadlineSummaryReport from "./HeadlineSummaryReport";
import WeatherReport from "./WeatherReport";

type WeatherReportData = components["schemas"]["WeatherReport"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

export interface HeadlineLeadInProps {
  headline: ResolvedHeadline | null;
  weatherReport: WeatherReportData | null;
  safetyRecommendation?: SafetyRecommendation | null;
  showHeadlineSkeleton?: boolean;
  showWeatherSkeleton?: boolean;
  class?: string;
}

function HeadlineSummarySkeleton(): JSX.Element {
  return (
    <Card
      data-testid="headline-summary-chrome"
      class="relative rounded-md border border-border/50 bg-card p-3 pb-8 pr-8"
    >
      <section
        data-testid="headline-summary-skeleton"
        class="space-y-2"
        aria-hidden="true"
      >
        <Skeleton class="h-4 w-full" />
        <Skeleton class="h-4 w-11/12" />
        <Skeleton class="h-4 w-4/5" />
      </section>
    </Card>
  );
}

export default function HeadlineLeadIn(props: HeadlineLeadInProps): JSX.Element {
  const weatherSlotVisible = () =>
    props.weatherReport !== null || props.showWeatherSkeleton === true;
  const hasHeadline = () =>
    props.headline !== null ||
    props.showHeadlineSkeleton === true ||
    weatherSlotVisible();

  if (!hasHeadline() && !weatherSlotVisible()) {
    return <></>;
  }

  const gridClass = () =>
    weatherSlotVisible()
      ? "grid grid-cols-1 gap-3 lg:grid-cols-[fit-content(28rem)_1fr]"
      : "grid grid-cols-1 gap-3";

  return (
    <section
      data-testid="headline-lead-in"
      class={`${gridClass()} ${props.class ?? ""}`.trim()}
    >
      <Show when={weatherSlotVisible()}>
        <WeatherReport
          report={props.showWeatherSkeleton ? null : props.weatherReport}
          safetyRecommendation={props.safetyRecommendation}
        />
      </Show>
      <Show when={hasHeadline()}>
        <Show
          when={props.headline}
          fallback={<HeadlineSummarySkeleton />}
        >
          {(headline) => (
            <Card
              data-testid="headline-summary-chrome"
              class="relative rounded-md border border-border/50 bg-card p-3 pb-8 pr-8"
            >
              <HeadlineSummaryReport headline={headline()} />
            </Card>
          )}
        </Show>
      </Show>
    </section>
  );
}
