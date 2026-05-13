import { createSignal, For, Show, type JSX } from "solid-js";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@opennotes/ui/components/ui/hover-card";
import type { components } from "~/lib/generated-types";
import type { RecentAnalysis } from "~/lib/api-client.server";
import { formatWeatherLabel, formatWeatherTextClass } from "~/lib/weather-labels";

type WeatherReport = NonNullable<RecentAnalysis["weather_report"]>;
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WeatherAxis = "truth" | "relevance" | "sentiment";

export interface GalleryHoverCardItem {
  headline_summary?: string | null;
  weather_report?: RecentAnalysis["weather_report"];
  safety_recommendation?: SafetyRecommendation | null;
}

interface GalleryHoverCardProps {
  item: GalleryHoverCardItem;
  href: string;
  class?: string;
  "data-testid"?: string;
  children: JSX.Element;
}

const WEATHER_AXES: Array<{ key: WeatherAxis; label: string }> = [
  { key: "truth", label: "Truth" },
  { key: "relevance", label: "Relevance" },
  { key: "sentiment", label: "Sentiment" },
];

function axisValue(report: WeatherReport, axis: WeatherAxis): string {
  return formatWeatherLabel(report[axis].label);
}

function SafetyRow(props: {
  safetyRecommendation: SafetyRecommendation | null | undefined;
}): JSX.Element {
  return (
    <div class="flex items-center justify-between gap-3">
      <span class="text-[11px] font-medium uppercase text-muted-foreground">
        Safety
      </span>
      <Show
        when={props.safetyRecommendation?.level}
        fallback={
          <span class="text-sm text-muted-foreground">Not available</span>
        }
      >
        {(level) => (
          <span class={formatWeatherTextClass(level()) + " text-sm font-medium"}>
            {formatWeatherLabel(level())}
          </span>
        )}
      </Show>
    </div>
  );
}

function WeatherAxes(props: { report: WeatherReport }): JSX.Element {
  return (
    <For each={WEATHER_AXES}>
      {(axis) => (
        <div class="flex items-center justify-between gap-3">
          <span class="text-[11px] font-medium uppercase text-muted-foreground">
            {axis.label}
          </span>
          <span class={formatWeatherTextClass(props.report[axis.key].label) + " text-sm font-medium"}>
            {axisValue(props.report, axis.key)}
          </span>
        </div>
      )}
    </For>
  );
}

export default function GalleryHoverCard(
  props: GalleryHoverCardProps,
): JSX.Element {
  const headline = () => props.item.headline_summary?.trim() ?? "";
  const hasContent = () =>
    props.item.weather_report != null ||
    props.item.safety_recommendation != null ||
    headline().length > 0;
  const [open, setOpen] = createSignal(false);
  let touchPointerIntent = false;

  if (!hasContent()) {
    return (
      <a
        data-testid={props["data-testid"]}
        href={props.href}
        class={props.class}
      >
        {props.children}
      </a>
    );
  }

  return (
    <HoverCard
      open={open()}
      onOpenChange={setOpen}
      openDelay={150}
      closeDelay={100}
    >
      <HoverCardTrigger
        as="a"
        data-testid={props["data-testid"]}
        href={props.href}
        class={props.class}
        onClick={(event) => {
          if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.altKey ||
            event.ctrlKey ||
            event.shiftKey
          ) {
            return;
          }
          window.location.assign(props.href);
        }}
        onPointerDown={(event) => {
          touchPointerIntent = event.pointerType === "touch";
          if (touchPointerIntent) setOpen(false);
        }}
        onFocusIn={() => {
          if (!touchPointerIntent) setOpen(true);
        }}
        onFocusOut={(event) => {
          const nextTarget = event.relatedTarget;
          if (
            nextTarget instanceof Node &&
            event.currentTarget.contains(nextTarget)
          ) {
            return;
          }
          touchPointerIntent = false;
          setOpen(false);
        }}
      >
        {props.children}
      </HoverCardTrigger>
      <HoverCardContent
        data-testid="gallery-hover-card"
        class="w-80 space-y-3 p-3"
      >
        <Show
          when={
            props.item.weather_report != null ||
            props.item.safety_recommendation != null
          }
        >
          <div class="space-y-2">
            <SafetyRow safetyRecommendation={props.item.safety_recommendation} />
            <Show when={props.item.weather_report}>
              {(report) => <WeatherAxes report={report()} />}
            </Show>
          </div>
        </Show>
        <Show when={headline().length > 0}>
          <p class="border-t border-border pt-3 text-sm leading-snug text-muted-foreground">
            {headline()}
          </p>
        </Show>
      </HoverCardContent>
    </HoverCard>
  );
}
