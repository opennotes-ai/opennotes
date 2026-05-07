import type { components } from "~/lib/generated-types";
import weatherLabelsJson from "./weather-labels.json";

type WeatherReport = components["schemas"]["WeatherReport"];
type WeatherAxisLabel =
  | WeatherReport["truth"]["label"]
  | WeatherReport["relevance"]["label"]
  | WeatherReport["sentiment"]["label"];

type WeatherLabelEntry = {
  axis: "truth" | "relevance" | "sentiment";
  label: string;
  variant: WeatherVariant;
};

type WeatherVariant = keyof typeof VARIANT_CLASSES;

export const VARIANT_CLASSES = {
  sky:     "inline-flex rounded-full bg-sky-500/10 px-2 py-0.5 text-[11px] font-medium text-sky-700",
  blue:    "inline-flex rounded-full bg-blue-500/10 px-2 py-0.5 text-[11px] font-medium text-blue-700",
  indigo:  "inline-flex rounded-full bg-indigo-500/10 px-2 py-0.5 text-[11px] font-medium text-indigo-700",
  stone:   "inline-flex rounded-full bg-stone-500/10 px-2 py-0.5 text-[11px] font-medium text-stone-700",
  rose:    "inline-flex rounded-full bg-rose-500/10 px-2 py-0.5 text-[11px] font-medium text-rose-700",
  emerald: "inline-flex rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-700",
  green:   "inline-flex rounded-full bg-green-500/10 px-2 py-0.5 text-[11px] font-medium text-green-700",
  teal:    "inline-flex rounded-full bg-teal-500/10 px-2 py-0.5 text-[11px] font-medium text-teal-700",
  cyan:    "inline-flex rounded-full bg-cyan-500/10 px-2 py-0.5 text-[11px] font-medium text-cyan-700",
  amber:   "inline-flex rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-700",
  slate:   "inline-flex rounded-full bg-slate-500/10 px-2 py-0.5 text-[11px] font-medium text-slate-700",
  orange:  "inline-flex rounded-full bg-orange-500/10 px-2 py-0.5 text-[11px] font-medium text-orange-700",
  violet:  "inline-flex rounded-full bg-violet-500/10 px-2 py-0.5 text-[11px] font-medium text-violet-700",
} as const satisfies Record<string, string>;

const DEFAULT_VARIANT: WeatherVariant = "slate";

const WEATHER_LABELS = weatherLabelsJson as Record<string, WeatherLabelEntry>;

function defaultTitleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatWeatherLabel(value: WeatherAxisLabel): string {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.label;
  return defaultTitleCase(String(value));
}

export function formatWeatherVariant(value: WeatherAxisLabel): WeatherVariant {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.variant;
  return DEFAULT_VARIANT;
}

export function formatWeatherBadgeClass(value: WeatherAxisLabel): string {
  return VARIANT_CLASSES[formatWeatherVariant(value)];
}

export function formatWeatherReadout(report: WeatherReport): string {
  return [
    formatWeatherLabel(report.truth.label),
    formatWeatherLabel(report.relevance.label),
    formatWeatherLabel(report.sentiment.label),
  ].join(" · ");
}
