import { For, Show, type JSX } from "solid-js";
import { Card, CardContent } from "@opennotes/ui/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@opennotes/ui/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@opennotes/ui/components/ui/tooltip";
import { Skeleton } from "@opennotes/ui/components/ui/skeleton";
import type { components } from "~/lib/generated-types";

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
  mapLabel: (value: WeatherAxisLabel) => string;
  valueClass: (value: WeatherAxisLabel) => string;
}

const TOOLTIP_COPY: Record<AxisType, string> = {
  truth:
    "Truth — How factually grounded the claim is. Higher = better-sourced; lower = misleading or unverified.",
  relevance:
    "Relevance — How on-topic the content is. Higher = insightful and on-topic; lower = drifting or off-topic.",
  sentiment:
    "Sentiment — The emotional tone of the content as a free-form descriptor.",
};

const AXES: AxisDefinition[] = [
  {
    axisType: "truth",
    heading: "Truth",
    tooltip: TOOLTIP_COPY.truth,
    mapLabel: mapTruthLabel,
    valueClass: valueClassForTruth,
  },
  {
    axisType: "relevance",
    heading: "Relevance",
    tooltip: TOOLTIP_COPY.relevance,
    mapLabel: mapRelevanceLabel,
    valueClass: valueClassForRelevance,
  },
  {
    axisType: "sentiment",
    heading: "Sentiment",
    tooltip: TOOLTIP_COPY.sentiment,
    mapLabel: mapSentimentLabel,
    valueClass: valueClassForSentiment,
  },
];

function formatLogprobProbability(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  const probability = Math.exp(value) * 100;
  return `${Math.round(probability * 100) / 100}%`;
}

function mapTruthLabel(value: WeatherAxisLabel): string {
  switch (value) {
    case "sourced":
      return "Sourced";
    case "mostly_factual":
      return "Mostly factual";
    case "self_reported":
      return "Self-reported";
    case "hearsay":
      return "Hearsay";
    case "misleading":
      return "Misleading";
    default:
      return String(value);
  }
}

function mapRelevanceLabel(value: WeatherAxisLabel): string {
  switch (value) {
    case "insightful":
      return "Insightful";
    case "on_topic":
      return "On topic";
    case "chatty":
      return "Chatty";
    case "drifting":
      return "Drifting";
    case "off_topic":
      return "Off topic";
    default:
      return String(value);
  }
}

function mapSentimentLabel(value: WeatherAxisLabel): string {
  return String(value);
}

function valueClassForTruth(value: WeatherAxisLabel): string {
  switch (value) {
    case "sourced":
      return "inline-flex rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700";
    case "mostly_factual":
      return "inline-flex rounded-full bg-lime-500/10 px-2 py-0.5 text-[11px] font-medium text-lime-700";
    case "self_reported":
      return "inline-flex rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground";
    case "hearsay":
      return "inline-flex rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700";
    case "misleading":
      return "inline-flex rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive";
    default:
      return "inline-flex rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-foreground";
  }
}

function valueClassForRelevance(value: WeatherAxisLabel): string {
  switch (value) {
    case "insightful":
      return "inline-flex rounded-full bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-700";
    case "on_topic":
      return "inline-flex rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700";
    case "chatty":
      return "inline-flex rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground";
    case "drifting":
      return "inline-flex rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700";
    case "off_topic":
      return "inline-flex rounded-full bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive";
    default:
      return "inline-flex rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-foreground";
  }
}

function valueClassForSentiment(_value: WeatherAxisLabel): string {
  return "inline-flex rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-foreground";
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

  return (
    <Tooltip>
      <TooltipTrigger
        as={TableRow}
        data-testid={`weather-axis-card-${props.axis.axisType}`}
      >
        <TableCell class="w-full">
          <Show
            when={axisData()}
            fallback={
              <span
                data-testid={`weather-${props.axis.axisType}-value`}
                class="text-sm font-medium text-muted-foreground"
              >
                Not available
              </span>
            }
          >
            {(axisValue) => {
              const label = () => props.axis.mapLabel(axisValue().label);
              return (
                <div class="flex flex-wrap items-center gap-2">
                  <span
                    data-testid={`weather-${props.axis.axisType}-value`}
                    class={props.axis.valueClass(axisValue().label)}
                    title={axisValue().label}
                  >
                    {label()}
                  </span>
                  <Show when={confidence() !== null}>
                    <span
                      data-testid={`weather-${props.axis.axisType}-confidence`}
                      class="text-[11px] text-muted-foreground"
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
                          const alternativeLabel = props.axis.mapLabel(
                            alternative.label as WeatherAxisLabel,
                          );
                          const alternativeConfidence =
                            formatLogprobProbability(alternative.logprob);
                          return (
                            <li class="inline-flex rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
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
                </div>
              );
            }}
          </Show>
        </TableCell>
      </TooltipTrigger>
      <TooltipContent class="max-w-xs text-xs leading-snug">
        {props.axis.tooltip}
      </TooltipContent>
    </Tooltip>
  );
}

function WeatherReportSkeleton(props: { class?: string }): JSX.Element {
  return (
    <Card
      data-testid="weather-report-skeleton"
      class={props.class}
      aria-hidden="true"
    >
      <CardContent class="p-2">
        <Table>
          <TableBody>
            <TableRow data-testid="weather-skeleton-truth">
              <TableCell>
                <Skeleton class="h-4 w-20 rounded-full" />
              </TableCell>
            </TableRow>
            <TableRow data-testid="weather-skeleton-relevance">
              <TableCell>
                <Skeleton class="h-4 w-20 rounded-full" />
              </TableCell>
            </TableRow>
            <TableRow data-testid="weather-skeleton-sentiment">
              <TableCell>
                <Skeleton class="h-4 w-20 rounded-full" />
              </TableCell>
            </TableRow>
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
        <Card data-testid="weather-report" class={props.class}>
          <CardContent class="p-2">
            <Table>
              <TableBody>
                <For each={AXES}>
                  {(axis) => <AxisRow report={report()} axis={axis} />}
                </For>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </Show>
  );
}
