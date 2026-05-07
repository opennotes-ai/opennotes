import { For, Show, type JSX } from "solid-js";
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
  mapLabel: (value: WeatherAxisLabel) => string;
  valueClass: (value: WeatherAxisLabel) => string;
}

const AXES: AxisDefinition[] = [
  {
    axisType: "truth",
    heading: "Truth",
    mapLabel: mapTruthLabel,
    valueClass: valueClassForTruth,
  },
  {
    axisType: "relevance",
    heading: "Relevance",
    mapLabel: mapRelevanceLabel,
    valueClass: valueClassForRelevance,
  },
  {
    axisType: "sentiment",
    heading: "Sentiment",
    mapLabel: mapSentimentLabel,
    valueClass: valueClassForSentiment,
  },
];

function formatLogprob(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) {
    return null;
  }
  return `logp ${value.toFixed(2)}`;
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

interface AxisCardProps {
  report: WeatherReportData | null;
  axisType: AxisType;
  heading: string;
  mapLabel: (value: WeatherAxisLabel) => string;
  valueClass: (value: WeatherAxisLabel) => string;
}

function AxisCard(props: AxisCardProps): JSX.Element {
  const axis = (): WeatherAxis | null => {
    if (!props.report) return null;
    switch (props.axisType) {
      case "truth":
        return props.report.truth as WeatherAxisTruth;
      case "relevance":
        return props.report.relevance as WeatherAxisRelevance;
      case "sentiment":
        return props.report.sentiment as WeatherAxisSentiment;
    }
  };

  const confidence = () => formatLogprob(axis()?.logprob);
  const alternatives = () => safeAlternatives(axis());

  return (
    <section
      data-testid={`weather-axis-card-${props.axisType}`}
      class="rounded-md border border-border bg-card p-2"
    >
      <h4 class="mb-1 text-xs font-semibold text-muted-foreground">{props.heading}</h4>
      <Show
        when={axis()}
        fallback={
          <p
            data-testid={`weather-${props.axisType}-value`}
            class="text-sm font-medium text-muted-foreground"
          >
            Not available
          </p>
        }
      >
        {(axisValue) => {
          const label = () => props.mapLabel(axisValue().label);
          return (
            <div class="space-y-2">
              <p
                data-testid={`weather-${props.axisType}-value`}
                class={props.valueClass(axisValue().label)}
                title={axisValue().label}
              >
                {label()}
              </p>

              <Show when={confidence() !== null || alternatives().length > 0}>
                <div class="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                  <Show when={confidence() !== null}>
                    <span
                      data-testid={`weather-${props.axisType}-confidence`}
                    >
                      {confidence()}
                    </span>
                  </Show>
                </div>
              </Show>

              <Show when={alternatives().length > 0}>
                <ul
                  data-testid={`weather-${props.axisType}-alternatives`}
                  class="flex flex-wrap gap-2"
                >
                  <For each={alternatives()}>
                    {(alternative) => {
                      const alternativeLabel = props.mapLabel(
                        alternative.label as WeatherAxisLabel,
                      );
                      const alternativeConfidence = formatLogprob(
                        alternative.logprob,
                      );
                      return (
                        <li
                          class="inline-flex rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground"
                        >
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
    </section>
  );
}

function WeatherReportSkeleton(props: { class?: string }): JSX.Element {
  return (
    <div
      data-testid="weather-report-skeleton"
      class={`grid h-full min-h-[110px] grid-cols-3 gap-2 ${props.class ?? ""}`.trim()}
    >
      <div
        data-testid="weather-skeleton-truth"
        class="rounded-md border border-border bg-card p-3"
        aria-hidden="true"
      >
        <div class="skeleton-pulse-extra mb-2 h-4 w-16 rounded" />
        <div class="skeleton-pulse-extra-delay-1 mb-2 h-6 w-24 rounded-full" />
        <div class="flex items-center gap-2">
          <div class="skeleton-pulse-extra h-3 w-10 rounded" />
          <div class="skeleton-pulse-extra-delay-1 h-3 w-16 rounded" />
        </div>
      </div>
      <div
        data-testid="weather-skeleton-relevance"
        class="rounded-md border border-border bg-card p-3"
        aria-hidden="true"
      >
        <div class="skeleton-pulse-extra mb-2 h-4 w-20 rounded" />
        <div class="skeleton-pulse-extra-delay-2 mb-2 h-6 w-24 rounded-full" />
        <div class="flex items-center gap-2">
          <div class="skeleton-pulse-extra h-3 w-10 rounded" />
          <div class="skeleton-pulse-extra-delay-1 h-3 w-16 rounded" />
        </div>
      </div>
      <div
        data-testid="weather-skeleton-sentiment"
        class="rounded-md border border-border bg-card p-3"
        aria-hidden="true"
      >
        <div class="skeleton-pulse-extra mb-2 h-4 w-16 rounded" />
        <div class="skeleton-pulse-extra-delay-2 mb-2 h-6 w-24 rounded-full" />
        <div class="flex items-center gap-2">
          <div class="skeleton-pulse-extra h-3 w-10 rounded" />
          <div class="skeleton-pulse-extra-delay-1 h-3 w-14 rounded" />
        </div>
      </div>
    </div>
  );
}

export default function WeatherReport(props: WeatherReportProps): JSX.Element {
  return (
    <Show
      when={props.report}
      fallback={<WeatherReportSkeleton class={props.class} />}
    >
      {(report) => (
        <div
          data-testid="weather-report"
          class={`grid h-full min-h-[110px] grid-cols-3 gap-2 ${props.class ?? ""}`.trim()}
        >
          <For each={AXES}>
            {(axis) => (
              <AxisCard
                report={report()}
                axisType={axis.axisType}
                heading={axis.heading}
                mapLabel={axis.mapLabel}
                valueClass={axis.valueClass}
              />
            )}
          </For>
        </div>
      )}
    </Show>
  );
}
