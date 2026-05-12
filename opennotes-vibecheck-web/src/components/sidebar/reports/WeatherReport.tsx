import { For, Show, createSignal, type JSX } from "solid-js";
import { ChevronRight } from "lucide-solid";
import { WeatherHelpButton } from "./WeatherHelpButton";
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
  safetyPopoverOpen?: () => boolean;
  setSafetyPopoverOpen?: (v: boolean) => void;
  safetyPopoverContentId?: string;
  safetyLastTrigger?: () => "symbol" | "axis-pair";
}

function SafetyAxisRow(props: {
  safetyRecommendation: SafetyRecommendation | null | undefined;
  heading: string;
  store: SidebarStore | null;
  targetGroup: SectionGroupLabel;
  popoverOpen: () => boolean;
  setPopoverOpen: (v: boolean) => void;
  popoverContentId?: string;
  lastTrigger?: () => "symbol" | "axis-pair";
}): JSX.Element {
  const recommendation = () => props.safetyRecommendation ?? null;
  const popoverOpen = props.popoverOpen;
  const setPopoverOpen = props.setPopoverOpen;
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
    if (props.lastTrigger?.() !== "symbol") {
      queueMicrotask(() => triggerRef?.focus());
    }
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
            <PopoverContent id={props.popoverContentId} class="max-w-xs text-sm leading-snug pr-2 pb-2">
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
    const [localOpen, setLocalOpen] = createSignal(false);
    const popoverOpen = props.safetyPopoverOpen ?? localOpen;
    const setPopoverOpen = props.setSafetyPopoverOpen ?? setLocalOpen;
    return (
      <SafetyAxisRow
        safetyRecommendation={props.safetyRecommendation}
        heading={props.axis.heading}
        store={store}
        targetGroup={targetGroup}
        popoverOpen={popoverOpen}
        setPopoverOpen={setPopoverOpen}
        popoverContentId={props.safetyPopoverContentId}
        lastTrigger={props.safetyLastTrigger}
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
                <p class="flex-1">{expansion() ?? AXIS_DEFINITIONS[props.axis.axisType as keyof typeof AXIS_DEFINITIONS]?.description}</p>
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

        const [safetyPopoverOpen, setSafetyPopoverOpen] = createSignal(false);
        const store = useSidebarStore();
        const safetyTargetGroup: SectionGroupLabel = "Safety";
        const safetyPopoverContentId = "weather-safety-popover-content";
        const [lastSafetyTrigger, setLastSafetyTrigger] = createSignal<"symbol" | "axis-pair">("axis-pair");
        let symbolButtonRef: HTMLButtonElement | undefined;

        const setSafetyOpen = (open: boolean, trigger: "symbol" | "axis-pair" = "axis-pair") => {
          setSafetyPopoverOpen(open);
          if (open) {
            setLastSafetyTrigger(trigger);
            store?.setHighlightedGroup(safetyTargetGroup);
          } else {
            if (store?.highlightedGroup() === safetyTargetGroup) {
              store?.setHighlightedGroup(null);
            }
            queueMicrotask(() => {
              if (lastSafetyTrigger() === "symbol") {
                symbolButtonRef?.focus();
              }
            });
          }
        };

        const SAFETY_ARIA_LABEL: Record<SafetyLevel, string> = {
          safe: "Safety: Safe",
          mild: "Safety: Mild",
          caution: "Safety: Caution",
          unsafe: "Safety: Unsafe",
          unknown: "Safety: not available",
        };

        const symbolAriaLabel = () => SAFETY_ARIA_LABEL[level()];

        return (
          <div
            data-testid="weather-report"
            class={`relative inline-flex items-center gap-[10px] rounded-[14px] border border-border/50 bg-card px-[22px] py-4 pb-8 ${props.class ?? ""}`.trim()}
          >
            <button
              type="button"
              ref={(el: HTMLButtonElement) => { symbolButtonRef = el; }}
              class="flex-none flex items-center justify-center rounded-md bg-transparent border-0 p-0 cursor-pointer motion-safe:transition-[transform,box-shadow] motion-safe:duration-[220ms] motion-safe:ease-[cubic-bezier(0.22,1,0.36,1)] motion-safe:[@media(hover:hover)]:hover:[box-shadow:var(--card-hover-light)] motion-safe:[@media(hover:hover)]:hover:-translate-y-px motion-safe:focus-visible:[box-shadow:var(--card-hover-light)] motion-safe:focus-visible:-translate-y-px motion-safe:[@media(hover:hover)]:hover:dark:[box-shadow:var(--card-hover-dark-underlit)] motion-safe:focus-visible:dark:[box-shadow:var(--card-hover-dark-underlit)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              data-testid="weather-symbol-cell"
              aria-label={symbolAriaLabel()}
              aria-haspopup="dialog"
              aria-expanded={safetyPopoverOpen()}
              aria-controls={safetyPopoverContentId}
              style="width:clamp(80px,12.8vw,128px)"
              onClick={() => setSafetyOpen(true, "symbol")}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setSafetyOpen(true, "symbol"); }}
            >
              <WeatherSymbol
                level={level()}
                lobeColors={lobeColors()}
                size="100%"
                class="block w-full h-auto"
              />
            </button>
            <div data-testid="weather-axis-stack" class="flex flex-col gap-[14px] text-center min-w-[120px]">
              <For each={AXES}>
                {(axis) => (
                  <AxisRow
                    report={report()}
                    axis={axis}
                    safetyRecommendation={props.safetyRecommendation}
                    safetyPopoverOpen={safetyPopoverOpen}
                    setSafetyPopoverOpen={setSafetyOpen}
                    safetyPopoverContentId={safetyPopoverContentId}
                    safetyLastTrigger={lastSafetyTrigger}
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
