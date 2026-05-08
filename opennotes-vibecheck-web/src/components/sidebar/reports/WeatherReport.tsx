import { For, Show, type JSX } from "solid-js";
import { Card, CardContent } from "@opennotes/ui/components/ui/card";
import { FeedbackBell } from "../../feedback/FeedbackBell";
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@opennotes/ui/components/ui/table";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@opennotes/ui/components/ui/popover";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import type { components } from "~/lib/generated-types";
import {
  formatWeatherExpansion,
  formatWeatherLabel,
} from "~/lib/weather-labels";

type WeatherReportData = components["schemas"]["WeatherReport"];
type WeatherAxisTruth = components["schemas"]["WeatherAxisTruth"];
type WeatherAxisRelevance = components["schemas"]["WeatherAxisRelevance"];
type WeatherAxisSentiment = components["schemas"]["WeatherAxisSentiment"];
type WeatherAxisAlternativeTruth = components["schemas"]["WeatherAxisAlternativeTruth"];
type WeatherAxisAlternativeRelevance = components["schemas"]["WeatherAxisAlternativeRelevance"];
type WeatherAxisAlternativeSentiment = components["schemas"]["WeatherAxisAlternativeSentiment"];

type WeatherAxis =
  | WeatherAxisTruth
  | WeatherAxisRelevance
  | WeatherAxisSentiment;
type WeatherAxisLabel = WeatherAxis["label"];
type WeatherAxisAlternative =
  | WeatherAxisAlternativeTruth
  | WeatherAxisAlternativeRelevance
  | WeatherAxisAlternativeSentiment;

type AxisType = "truth" | "relevance" | "sentiment";

export interface WeatherReportProps {
  report: WeatherReportData | null;
  class?: string;
}

interface AxisDefinition {
  axisType: AxisType;
  heading: string;
  tooltip: string;
}

const TOOLTIP_COPY: Record<AxisType, string> = {
  truth:
    "Truth — Epistemic stance, not verdict. Whether claims are sourced, first-person, second-hand, or actively misleading — how the knowledge is held, regardless of whether it's ultimately right.",
  relevance:
    "Relevance — How tightly the discussion is tethered to the source. Insightful engagement, on-topic chatter, drift, or full topic abandonment.",
  sentiment:
    "Sentiment — The emotional register of the conversation. Read alongside the other axes; tone alone doesn't tell you much.",
};

const AXES: AxisDefinition[] = [
  {
    axisType: "truth",
    heading: "Truth",
    tooltip: TOOLTIP_COPY.truth,
  },
  {
    axisType: "relevance",
    heading: "Relevance",
    tooltip: TOOLTIP_COPY.relevance,
  },
  {
    axisType: "sentiment",
    heading: "Sentiment",
    tooltip: TOOLTIP_COPY.sentiment,
  },
];

function formatLogprobProbability(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  const probability = Math.exp(value) * 100;
  return `${Math.round(probability * 100) / 100}%`;
}

function safeAlternatives(axis: WeatherAxis | null): WeatherAxisAlternative[] {
  const alternatives = axis?.alternatives;
  if (!alternatives || alternatives.length === 0) return [];
  return alternatives.filter(
    (alternative): alternative is WeatherAxisAlternative =>
      Boolean(alternative.label && alternative.label.trim().length),
  );
}

interface AxisRowProps {
  report: WeatherReportData;
  axis: AxisDefinition;
}

function AxisRow(props: AxisRowProps): JSX.Element {
  const axisData = (): WeatherAxis | null => {
    switch (props.axis.axisType) {
      case "truth":
        return props.report.truth as WeatherAxisTruth;
      case "relevance":
        return props.report.relevance as WeatherAxisRelevance;
      case "sentiment":
        return props.report.sentiment as WeatherAxisSentiment;
    }
  };

  const confidence = () => formatLogprobProbability(axisData()?.logprob);
  const alternatives = () => safeAlternatives(axisData());
  const expansion = (): string | null => {
    const data = axisData();
    if (!data) return null;
    return formatWeatherExpansion(data.label as WeatherAxisLabel);
  };

  const evalContent = () => {
    const data = axisData();
    return (
      <span class="flex flex-wrap items-baseline gap-2">
        <span
          data-testid={`weather-${props.axis.axisType}-value`}
          class="font-condensed text-lg font-semibold"
        >
          {data ? formatWeatherLabel(data.label) : "Not available"}
        </span>
        <Show when={data && confidence() !== null}>
          <span
            data-testid={`weather-${props.axis.axisType}-confidence`}
            class="text-xs text-muted-foreground"
          >
            {confidence()}
          </span>
        </Show>
        <Show when={alternatives().length > 0}>
          <ul
            data-testid={`weather-${props.axis.axisType}-alternatives`}
            class="flex flex-wrap gap-1"
          >
            <For each={alternatives()}>
              {(alternative) => {
                const alternativeLabel = formatWeatherLabel(
                  alternative.label as WeatherAxisLabel,
                );
                const alternativeConfidence =
                  formatLogprobProbability(alternative.logprob);
                return (
                  <li class="inline-flex rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                    {alternativeLabel}
                    <Show when={alternativeConfidence !== null}>
                      <span> ({alternativeConfidence})</span>
                    </Show>
                  </li>
                );
              }}
            </For>
          </ul>
        </Show>
      </span>
    );
  };

  const placement = () =>
    props.axis.axisType === "sentiment" ? "top-start" : "bottom-start";

  return (
    <TableRow class="group">
      <Show
        when={axisData() && expansion() !== null}
        fallback={
          <td colSpan={2} class="p-0">
            <div class="flex w-full items-center justify-between gap-3 px-2 py-1.5">
              {evalContent()}
              <span
                aria-hidden="true"
                class="pr-3 text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
              >
                {props.axis.heading}
              </span>
            </div>
          </td>
        }
      >
        <td colSpan={2} class="p-0">
          <Popover placement={placement()}>
            <PopoverTrigger
              as="button"
              type="button"
              data-testid={`weather-axis-card-${props.axis.axisType}`}
              aria-label={`${props.axis.heading}: ${axisData() ? formatWeatherLabel(axisData()!.label) : ""}`}
              class="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left hover:bg-muted/40 focus-visible:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            >
              {evalContent()}
              <span
                aria-hidden="true"
                class="pr-3 text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
              >
                {props.axis.heading}
              </span>
            </PopoverTrigger>
            <PopoverContent class="max-w-xs text-sm leading-snug">
              {expansion()}
            </PopoverContent>
          </Popover>
        </td>
      </Show>
    </TableRow>
  );
}

function WeatherReportSkeleton(props: { class?: string }): JSX.Element {
  return (
    <Card
      data-testid="weather-report-skeleton"
      class={`border border-border/50 ${props.class ?? ""}`.trim()}
      aria-hidden="true"
    >
      <CardContent class="p-2">
        <Table>
          <TableBody>
            <For each={AXES}>
              {(axis) => (
                <TableRow data-testid={`weather-skeleton-${axis.axisType}`}>
                  <TableCell
                    data-testid={`weather-skeleton-${axis.axisType}-label`}
                    class="whitespace-nowrap pr-3 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground"
                  >
                    {axis.heading.toUpperCase()}
                  </TableCell>
                  <TableCell class="w-full">
                    <Skeleton class="h-4 w-20 rounded-full" />
                  </TableCell>
                </TableRow>
              )}
            </For>
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

export default function WeatherReport(props: WeatherReportProps): JSX.Element {
  return (
    <Show
      when={props.report}
      fallback={<WeatherReportSkeleton class={props.class} />}
    >
      {(report) => (
        <Card data-testid="weather-report" class={`relative border border-border/50 ${props.class ?? ""}`.trim()}>
          <CardContent class="p-2">
            <Table>
              <TableBody>
                <For each={AXES}>
                  {(axis) => <AxisRow report={report()} axis={axis} />}
                </For>
              </TableBody>
            </Table>
          </CardContent>
          <FeedbackBell bell_location="card:weather" />
        </Card>
      )}
    </Show>
  );
}
