import { For, Show, createSignal, type JSX } from "solid-js";
import { ChevronRight } from "lucide-solid";
import { Card, CardContent } from "@opennotes/ui/components/ui/card";
import { WeatherHelpButton, TOOLTIP_COPY } from "./WeatherHelpButton";
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
  formatWeatherTextClass,
} from "~/lib/weather-labels";
import { useSidebarStore } from "../SidebarStoreProvider";
import type { SectionGroupLabel, SidebarStore } from "../sidebar-store";

type WeatherReportData = components["schemas"]["WeatherReport"];
type WeatherAxisTruth = components["schemas"]["WeatherAxisTruth"];
type WeatherAxisRelevance = components["schemas"]["WeatherAxisRelevance"];
type WeatherAxisSentiment = components["schemas"]["WeatherAxisSentiment"];
type WeatherAxisAlternativeTruth = components["schemas"]["WeatherAxisAlternativeTruth"];
type WeatherAxisAlternativeRelevance = components["schemas"]["WeatherAxisAlternativeRelevance"];
type WeatherAxisAlternativeSentiment = components["schemas"]["WeatherAxisAlternativeSentiment"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

type WeatherAxis =
  | WeatherAxisTruth
  | WeatherAxisRelevance
  | WeatherAxisSentiment;
type WeatherAxisLabel = WeatherAxis["label"];
type WeatherAxisAlternative =
  | WeatherAxisAlternativeTruth
  | WeatherAxisAlternativeRelevance
  | WeatherAxisAlternativeSentiment;

type AxisType = "safety" | "truth" | "relevance" | "sentiment";

const AXIS_TO_GROUP: Record<AxisType, SectionGroupLabel> = {
  safety: "Safety",
  truth: "Facts/claims",
  relevance: "Tone/dynamics",
  sentiment: "Opinions/sentiments",
};

export interface WeatherReportProps {
  report: WeatherReportData | null;
  safetyRecommendation?: SafetyRecommendation | null;
  class?: string;
}

interface AxisDefinition {
  axisType: AxisType;
  heading: string;
}

const AXES: AxisDefinition[] = [
  {
    axisType: "safety",
    heading: "Safety",
  },
  {
    axisType: "truth",
    heading: "Truth",
  },
  {
    axisType: "relevance",
    heading: "Relevance",
  },
  {
    axisType: "sentiment",
    heading: "Sentiment",
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
  safetyRecommendation?: SafetyRecommendation | null;
}

function SafetyAxisRow(props: {
  safetyRecommendation: SafetyRecommendation | null | undefined;
  heading: string;
  store: SidebarStore | null;
  targetGroup: SectionGroupLabel;
}): JSX.Element {
  const recommendation = () => props.safetyRecommendation ?? null;
  const [popoverOpen, setPopoverOpen] = createSignal(false);
  let triggerRef: HTMLButtonElement | undefined;

  const expansion = (): string | null => {
    const rec = recommendation();
    if (!rec) return null;
    return formatWeatherExpansion(rec.level) ?? rec.rationale;
  };

  const ariaLabel = () => {
    const rec = recommendation();
    if (!rec) return props.heading;
    return `${props.heading}: ${formatWeatherLabel(rec.level)}`;
  };

  const onFocusClick = () => {
    setPopoverOpen(false);
    props.store?.setHighlightedGroup(null);
    props.store?.isolateGroup(props.targetGroup);
    queueMicrotask(() => triggerRef?.focus());
  };

  return (
    <TableRow class="group">
      <Show
        when={recommendation()}
        fallback={
          <td colSpan={2} class="p-0">
            <div class="flex w-full items-center justify-between gap-3 px-2 py-1.5">
              <span class="flex flex-wrap items-baseline gap-2">
                <span
                  data-testid="weather-safety-value"
                  class="font-condensed text-lg font-semibold"
                >
                  Not available
                </span>
              </span>
              <span
                aria-hidden="true"
                class="cursor-default select-none pr-3 text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
              >
                {props.heading}
              </span>
            </div>
          </td>
        }
      >
        {(rec) => (
          <td colSpan={2} class="p-0">
            <Popover
              placement="bottom-start"
              open={popoverOpen()}
              onOpenChange={(o) => {
                setPopoverOpen(o);
                if (o) {
                  props.store?.setHighlightedGroup(props.targetGroup);
                } else if (props.store?.highlightedGroup() === props.targetGroup) {
                  props.store?.setHighlightedGroup(null);
                }
              }}
            >
              <PopoverTrigger
                as="button"
                ref={(el: HTMLButtonElement) => { triggerRef = el; }}
                type="button"
                data-testid="weather-axis-card-safety"
                aria-label={ariaLabel()}
                class="flex w-full items-center gap-3 px-2 py-1.5 text-left rounded-md hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <span
                  data-testid="weather-safety-value"
                  class={formatWeatherTextClass(rec().level) + " font-condensed text-lg font-semibold"}
                >
                  {formatWeatherLabel(rec().level)}
                </span>
                <span
                  aria-hidden="true"
                  class="cursor-default ml-auto pr-3 select-none text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
                >
                  {props.heading}
                </span>
              </PopoverTrigger>
              <PopoverContent class="max-w-xs text-sm leading-snug pr-2 pb-2">
                <div class="flex items-end gap-2">
                  <p class="flex-1">{expansion() ?? props.heading}</p>
                  <Show when={props.store !== null}>
                    <button
                      type="button"
                      data-testid="weather-safety-focus"
                      aria-label="Focus this section"
                      class="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={onFocusClick}
                    >
                      <ChevronRight class="size-4" aria-hidden="true" />
                    </button>
                  </Show>
                </div>
              </PopoverContent>
            </Popover>
          </td>
        )}
      </Show>
    </TableRow>
  );
}

function AxisRow(props: AxisRowProps): JSX.Element {
  const store = useSidebarStore();
  const targetGroup = AXIS_TO_GROUP[props.axis.axisType];

  if (props.axis.axisType === "safety") {
    return (
      <SafetyAxisRow
        safetyRecommendation={props.safetyRecommendation}
        heading={props.axis.heading}
        store={store}
        targetGroup={targetGroup}
      />
    );
  }

  const [popoverOpen, setPopoverOpen] = createSignal(false);
  let triggerRef: HTMLButtonElement | undefined;

  const axisData = (): WeatherAxis | null => {
    switch (props.axis.axisType) {
      case "truth":
        return props.report.truth as WeatherAxisTruth;
      case "relevance":
        return props.report.relevance as WeatherAxisRelevance;
      case "sentiment":
        return props.report.sentiment as WeatherAxisSentiment;
      default:
        return null;
    }
  };

  const confidence = () => formatLogprobProbability(axisData()?.logprob);
  const alternatives = () => safeAlternatives(axisData());
  const expansion = (): string | null => {
    const data = axisData();
    if (!data) return null;
    return formatWeatherExpansion(data.label as WeatherAxisLabel);
  };

  const ariaLabel = () => {
    const data = axisData();
    if (!data) return props.axis.heading;
    const label = formatWeatherLabel(data.label);
    const conf = confidence();
    return conf
      ? `${props.axis.heading}: ${label}, ${conf}`
      : `${props.axis.heading}: ${label}`;
  };

  const placement = () =>
    props.axis.axisType === "sentiment" ? "top-start" : "bottom-start";

  const onFocusClick = () => {
    setPopoverOpen(false);
    store?.setHighlightedGroup(null);
    store?.isolateGroup(targetGroup);
    queueMicrotask(() => triggerRef?.focus());
  };

  return (
    <TableRow class="group">
      <Show
        when={axisData()}
        fallback={
          <td colSpan={2} class="p-0">
            <div class="flex w-full items-center justify-between gap-3 px-2 py-1.5">
              <span class="flex flex-wrap items-baseline gap-2">
                <span
                  data-testid={`weather-${props.axis.axisType}-value`}
                  class="font-condensed text-lg font-semibold"
                >
                  Not available
                </span>
              </span>
              <span
                aria-hidden="true"
                class="cursor-default select-none pr-3 text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
              >
                {props.axis.heading}
              </span>
            </div>
          </td>
        }
      >
        {(data) => (
          <td colSpan={2} class="p-0">
            <Popover
              placement={placement()}
              open={popoverOpen()}
              onOpenChange={(o) => {
                setPopoverOpen(o);
                if (o) {
                  store?.setHighlightedGroup(targetGroup);
                } else if (store?.highlightedGroup() === targetGroup) {
                  store?.setHighlightedGroup(null);
                }
              }}
            >
              <PopoverTrigger
                as="button"
                ref={(el: HTMLButtonElement) => { triggerRef = el; }}
                type="button"
                data-testid={`weather-axis-card-${props.axis.axisType}`}
                aria-label={ariaLabel()}
                class="flex w-full items-center gap-3 px-2 py-1.5 text-left rounded-md hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <span
                  data-testid={`weather-${props.axis.axisType}-value`}
                  class={`font-condensed ${formatWeatherTextClass(data().label)}`}
                >
                  {formatWeatherLabel(data().label)}
                </span>
                <Show when={confidence() !== null}>
                  <span
                    data-testid={`weather-${props.axis.axisType}-confidence`}
                    class="text-xs text-muted-foreground"
                  >
                    {confidence()}
                  </span>
                </Show>
                <span
                  aria-hidden="true"
                  class="cursor-default ml-auto pr-3 select-none text-xs uppercase tracking-[0.06em] text-muted-foreground/70"
                >
                  {props.axis.heading}
                </span>
              </PopoverTrigger>
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
              <PopoverContent class="max-w-xs text-sm leading-snug pr-2 pb-2">
                <div class="flex items-end gap-2">
                  <p class="flex-1">{expansion() ?? TOOLTIP_COPY[props.axis.axisType as keyof typeof TOOLTIP_COPY]}</p>
                  <Show when={store !== null}>
                    <button
                      type="button"
                      data-testid={`weather-${props.axis.axisType}-focus`}
                      aria-label="Focus this section"
                      class="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={onFocusClick}
                    >
                      <ChevronRight class="size-4" aria-hidden="true" />
                    </button>
                  </Show>
                </div>
              </PopoverContent>
            </Popover>
          </td>
        )}
      </Show>
    </TableRow>
  );
}

const WORD_SHAPES: Record<AxisType, number[]> = {
  safety: [56],
  truth: [80, 56],
  relevance: [72, 48],
  sentiment: [64],
};

function WeatherReportSkeleton(props: { class?: string }): JSX.Element {
  return (
    <Card
      data-testid="weather-report-skeleton"
      class={`relative border border-border/50 ${props.class ?? ""}`.trim()}
    >
      <CardContent class="p-2" aria-hidden="true">
        <Table>
          <TableBody>
            <For each={AXES}>
              {(axis) => (
                <TableRow data-testid={`weather-skeleton-${axis.axisType}`}>
                  <TableCell class="w-full px-2 py-1.5">
                    <div
                      data-testid={`weather-skeleton-${axis.axisType}-words`}
                      class="flex items-center gap-1.5"
                    >
                      <For each={WORD_SHAPES[axis.axisType]}>
                        {(w) => <Skeleton class="h-4 rounded bg-muted-foreground/25" style={{ width: `${w}px` }} />}
                      </For>
                    </div>
                  </TableCell>
                  <TableCell
                    data-testid={`weather-skeleton-${axis.axisType}-label`}
                    class="whitespace-nowrap pr-3 text-xs font-semibold uppercase tracking-[0.06em] text-muted-foreground/70 text-right"
                  >
                    {axis.heading.toUpperCase()}
                  </TableCell>
                </TableRow>
              )}
            </For>
          </TableBody>
        </Table>
      </CardContent>
      <WeatherHelpButton />
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
        <Card data-testid="weather-report" class={`relative border border-border/50 pb-8 ${props.class ?? ""}`.trim()}>
          <CardContent class="p-2">
            <Table>
              <TableBody>
                <For each={AXES}>
                  {(axis) => (
                    <AxisRow
                      report={report()}
                      axis={axis}
                      safetyRecommendation={props.safetyRecommendation}
                    />
                  )}
                </For>
              </TableBody>
            </Table>
          </CardContent>
          <WeatherHelpButton />
        </Card>
      )}
    </Show>
  );
}
