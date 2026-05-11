import { For, Show, createSignal, type JSX } from "solid-js";
import { ChevronRight } from "lucide-solid";
import { WeatherHelpButton, TOOLTIP_COPY } from "./WeatherHelpButton";
import { WeatherSymbol, type SafetyLevel } from "./WeatherSymbol";
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
  formatWeatherVariant,
  getVariantHex,
  AXIS_DEFINITIONS,
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
  { axisType: "safety",    heading: AXIS_DEFINITIONS.safety.heading },
  { axisType: "truth",     heading: AXIS_DEFINITIONS.truth.heading },
  { axisType: "relevance", heading: AXIS_DEFINITIONS.relevance.heading },
  { axisType: "sentiment", heading: AXIS_DEFINITIONS.sentiment.heading },
];

function variantHex(label: string): string {
  const variant = formatWeatherVariant(label);
  return getVariantHex(variant);
}

function safetyLevel(rec: SafetyRecommendation | null | undefined): SafetyLevel {
  const level = rec?.level;
  if (level === "safe" || level === "mild" || level === "caution" || level === "unsafe") {
    return level;
  }
  return "unknown";
}

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
    <div class="pair">
      <Show
        when={recommendation()}
        fallback={
          <div class="flex flex-col items-center">
            <span
              aria-hidden="true"
              class="cursor-default select-none text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground font-condensed font-medium leading-tight"
            >
              {props.heading}
            </span>
            <span
              data-testid="weather-safety-value"
              class="font-serif font-semibold text-[1.05rem] text-foreground leading-snug mt-0.5"
            >
              Not available
            </span>
          </div>
        }
      >
        {(rec) => (
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
              class="flex flex-col items-center w-full rounded-md hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 px-1 py-0.5"
            >
              <span
                aria-hidden="true"
                class="cursor-default select-none text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground font-condensed font-medium leading-tight"
              >
                {props.heading}
              </span>
              <span
                data-testid="weather-safety-value"
                class="font-serif font-semibold text-[1.05rem] text-foreground leading-snug mt-0.5"
              >
                {formatWeatherLabel(rec().level)}
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
        )}
      </Show>
    </div>
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
    <div class="pair">
      <Show
        when={axisData()}
        fallback={
          <div class="flex flex-col items-center">
            <span
              aria-hidden="true"
              class="cursor-default select-none text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground font-condensed font-medium leading-tight"
            >
              {props.axis.heading}
            </span>
            <span
              data-testid={`weather-${props.axis.axisType}-value`}
              class="font-serif font-semibold text-[1.05rem] text-foreground leading-snug mt-0.5"
            >
              Not available
            </span>
          </div>
        }
      >
        {(data) => (
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
              class="flex flex-col items-center w-full rounded-md hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 px-1 py-0.5"
            >
              <span
                aria-hidden="true"
                class="cursor-default select-none text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground font-condensed font-medium leading-tight"
              >
                {props.axis.heading}
              </span>
              <span
                data-testid={`weather-${props.axis.axisType}-value`}
                class="font-serif font-semibold text-[1.05rem] text-foreground leading-snug mt-0.5"
              >
                {formatWeatherLabel(data().label)}
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
        )}
      </Show>
    </div>
  );
}

const SKELETON_WORD_SHAPES: Record<AxisType, number[]> = {
  safety:    [56],
  truth:     [80, 56],
  relevance: [72, 48],
  sentiment: [64],
};

function WeatherReportSkeleton(props: { class?: string }): JSX.Element {
  return (
    <div
      data-testid="weather-report-skeleton"
      class={`relative inline-flex items-center gap-[10px] rounded-[14px] border border-border/50 bg-card px-[22px] py-4 ${props.class ?? ""}`.trim()}
    >
      <div
        data-testid="weather-skeleton-symbol-cell"
        class="flex-none flex items-center justify-center"
        style="width:clamp(80px,12.8vw,128px)"
      >
        <Skeleton class="rounded-full" style="width:clamp(80px,12.8vw,128px);height:clamp(80px,12.8vw,128px);" />
      </div>
      <div aria-hidden="true" data-testid="weather-skeleton-axis-stack" class="flex flex-col gap-[14px] text-center min-w-[120px]">
        <For each={AXES}>
          {(axis) => (
            <div
              data-testid={`weather-skeleton-${axis.axisType}`}
              data-slot="table-row"
              class="flex flex-col items-center"
            >
              <span
                data-testid={`weather-skeleton-${axis.axisType}-label`}
                data-slot="table-cell"
                class="text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground/70 font-condensed font-medium"
              >
                {axis.heading.toUpperCase()}
              </span>
              <div
                data-testid={`weather-skeleton-${axis.axisType}-words`}
                data-slot="table-cell"
                class="flex items-center gap-1.5 mt-0.5"
              >
                <For each={SKELETON_WORD_SHAPES[axis.axisType]}>
                  {(w) => <Skeleton class="h-4 rounded bg-muted-foreground/25" style={{ width: `${w}px` }} />}
                </For>
              </div>
            </div>
          )}
        </For>
      </div>
      <WeatherHelpButton />
    </div>
  );
}

export default function WeatherReport(props: WeatherReportProps): JSX.Element {
  return (
    <Show
      when={props.report}
      fallback={<WeatherReportSkeleton class={props.class} />}
    >
      {(report) => {
        const truthLabel = () => report().truth?.label ?? "";
        const relevanceLabel = () => report().relevance?.label ?? "";
        const sentimentLabel = () => report().sentiment?.label ?? "";

        const lobeColors = (): [string, string, string] => [
          variantHex(truthLabel()),
          variantHex(relevanceLabel()),
          variantHex(sentimentLabel()),
        ];

        const level = () => safetyLevel(props.safetyRecommendation);

        return (
          <div
            data-testid="weather-report"
            class={`relative inline-flex items-center gap-[10px] rounded-[14px] border border-border/50 bg-card px-[22px] py-4 pb-8 ${props.class ?? ""}`.trim()}
          >
            <div
              class="flex-none flex items-center justify-center"
              data-testid="weather-symbol-cell"
              style="width:clamp(80px,12.8vw,128px)"
            >
              <WeatherSymbol
                level={level()}
                lobeColors={lobeColors()}
                size="100%"
                class="block w-full h-auto"
              />
            </div>
            <div data-testid="weather-axis-stack" class="flex flex-col gap-[14px] text-center min-w-[120px]">
              <For each={AXES}>
                {(axis) => (
                  <AxisRow
                    report={report()}
                    axis={axis}
                    safetyRecommendation={props.safetyRecommendation}
                  />
                )}
              </For>
            </div>
            <WeatherHelpButton />
          </div>
        );
      }}
    </Show>
  );
}
