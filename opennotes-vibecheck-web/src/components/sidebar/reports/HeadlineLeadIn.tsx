import { Show, type JSX } from "solid-js";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import type { components } from "~/lib/generated-types";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import HeadlineSummaryReport from "./HeadlineSummaryReport";
import WeatherReport from "./WeatherReport";

type WeatherReportData = components["schemas"]["WeatherReport"];

export interface HeadlineLeadInProps {
  headline: ResolvedHeadline | null;
  weatherReport: WeatherReportData | null;
  showHeadlineSkeleton?: boolean;
  showWeatherSkeleton?: boolean;
  class?: string;
}

function HeadlineSummarySkeleton(): JSX.Element {
  return (
    <section
      data-testid="headline-summary-skeleton"
      class="space-y-2"
      aria-hidden="true"
    >
      <Skeleton class="h-4 w-full" />
      <Skeleton class="h-4 w-11/12" />
      <Skeleton class="h-4 w-4/5" />
    </section>
  );
}

export default function HeadlineLeadIn(props: HeadlineLeadInProps): JSX.Element {
  const hasHeadline = () => props.headline !== null || props.showHeadlineSkeleton === true;
  const hasWeather = () => props.weatherReport !== null || props.showWeatherSkeleton === true;

  if (!hasHeadline() && !hasWeather()) {
    return <></>;
  }

  return (
    <section
      data-testid="headline-lead-in"
      class={`grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] ${props.class ?? ""}`.trim()}
    >
      <Show when={hasWeather()}>
        <WeatherReport
          report={props.showWeatherSkeleton ? null : props.weatherReport}
          class="grid-cols-3 lg:grid-cols-1"
        />
      </Show>
      <Show when={hasHeadline()}>
        <Show
          when={props.headline}
          fallback={<HeadlineSummarySkeleton />}
        >
          {(headline) => (
            <div
              data-testid="headline-summary-chrome"
              class="rounded-md border border-border bg-card p-3"
            >
              <HeadlineSummaryReport headline={headline()} />
            </div>
          )}
        </Show>
      </Show>
    </section>
  );
}
