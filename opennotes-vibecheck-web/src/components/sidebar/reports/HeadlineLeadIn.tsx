import { Show, type JSX } from "solid-js";
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
      class="rounded-md border border-border bg-card p-3"
      aria-hidden="true"
    >
      <div class="skeleton-pulse-extra mb-2 h-4 w-1/4 rounded" />
      <div class="space-y-2">
        <div class="skeleton-pulse-extra-delay-1 h-3 w-full rounded" />
        <div class="skeleton-pulse-extra-delay-2 h-3 w-11/12 rounded" />
        <div class="skeleton-pulse-extra-delay-1 h-3 w-4/5 rounded" />
      </div>
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
          class="min-h-[110px] grid-cols-3 lg:grid-cols-1"
        />
      </Show>
      <Show when={hasHeadline()}>
        <Show
          when={props.headline}
          fallback={<HeadlineSummarySkeleton />}
        >
          {(headline) => <HeadlineSummaryReport headline={headline()} />}
        </Show>
      </Show>
    </section>
  );
}
