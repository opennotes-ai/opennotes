import type { JSX } from "solid-js";
import { Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import { WeatherSymbol } from "~/components/sidebar/reports/WeatherSymbol";
import { safetyLevel, lobeColors } from "~/lib/weather-symbol-derive";
import GalleryHoverCard from "./GalleryHoverCard";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WeatherReport = components["schemas"]["WeatherReport"];

const NEUTRAL_LOBE_COLORS: [string, string, string] = ["#e5e7eb", "#e5e7eb", "#e5e7eb"];

export interface GalleryCardProps {
  href: string;
  title: string;
  snippet: string | null | undefined;
  screenshotUrl: string | null | undefined;
  screenshotFallback?: JSX.Element;
  safetyRecommendation: SafetyRecommendation | null | undefined;
  weatherReport: WeatherReport | null | undefined;
  testid?: string;
  class?: string;
}

export default function GalleryCard(props: GalleryCardProps): JSX.Element {
  const level = () => safetyLevel(props.safetyRecommendation);
  const symbolColors = () =>
    props.weatherReport != null
      ? lobeColors(props.weatherReport)
      : NEUTRAL_LOBE_COLORS;

  const hoverCardItem = () => ({
    headline_summary: null,
    weather_report: props.weatherReport,
    safety_recommendation: props.safetyRecommendation,
  });

  return (
    <GalleryHoverCard
      item={hoverCardItem()}
      href={props.href}
      data-testid={props.testid}
      class={props.class}
    >
      <div
        style={{
          display: "flex",
          width: "428px",
          height: "169px",
          "border-radius": "2px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: "50%",
            "flex-shrink": "0",
            "min-height": "0",
            "min-width": "0",
          }}
        >
          <Show
            when={props.screenshotUrl}
            fallback={
              <div
                style={{ width: "100%", height: "100%" }}
                class="bg-muted"
              >
                {props.screenshotFallback}
              </div>
            }
          >
            {(url) => (
              <div
                role="img"
                aria-label={props.title}
                style={{
                  width: "100%",
                  height: "100%",
                  "background-image": `url(${url()})`,
                  "background-size": "200%",
                  "background-position": "top center",
                  "background-repeat": "no-repeat",
                }}
              />
            )}
          </Show>
        </div>

        <div
          style={{
            width: "50%",
            "min-height": "0",
            "min-width": "0",
            display: "grid",
            "grid-template-rows": "40% 1fr",
          }}
        >
          <div
            style={{
              padding: "2px",
              overflow: "hidden",
              "border-bottom": "1px solid var(--color-border, #e5e7eb)",
              "min-height": "0",
              "min-width": "0",
              display: "flex",
              "align-items": "center",
              "justify-content": "center",
            }}
          >
            <div
              style={{
                height: "100%",
                "aspect-ratio": "1 / 1",
                display: "block",
                "max-width": "100%",
                "max-height": "100%",
              }}
            >
              <WeatherSymbol
                level={level()}
                lobeColors={symbolColors()}
                size="100%"
              />
            </div>
          </div>

          <div
            style={{
              padding: "14px",
              overflow: "hidden",
              "min-height": "0",
              "min-width": "0",
              display: "flex",
              "flex-direction": "column",
              gap: "4px",
            }}
          >
            <p class="line-clamp-2 text-sm font-medium leading-snug">
              {props.title}
            </p>
            <Show when={props.snippet}>
              {(snippet) => (
                <p class="line-clamp-2 text-xs text-muted-foreground">
                  {snippet()}
                </p>
              )}
            </Show>
          </div>
        </div>
      </div>
    </GalleryHoverCard>
  );
}
