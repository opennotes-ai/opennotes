import { Show, type JSX } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import type { components } from "~/lib/generated-types";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import { HighlightsCard } from "~/components/highlights/HighlightsCard";
import { tryUseHighlights } from "~/components/highlights/HighlightsStoreProvider";
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
  const highlightsStore = tryUseHighlights();
  const hasHighlights = () => (highlightsStore?.items().length ?? 0) > 0;

  const weatherSlotVisible = () =>
    props.weatherReport !== null || props.showWeatherSkeleton === true;
  const hasHeadline = () =>
    props.headline !== null ||
    props.showHeadlineSkeleton === true ||
    weatherSlotVisible();

  const gridClass = () =>
    weatherSlotVisible()
      ? "grid items-start grid-cols-1 gap-3 lg:grid-cols-[fit-content(28rem)_1fr]"
      : "grid grid-cols-1 gap-3";

  return (
    <Show when={hasHeadline() || weatherSlotVisible()}>
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
          <div class="flex min-w-0 flex-col gap-3">
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
            <Show when={hasHighlights()}>
              <HighlightsCard />
            </Show>
          </div>
        </Show>
      </section>
    </Show>
  );
}
