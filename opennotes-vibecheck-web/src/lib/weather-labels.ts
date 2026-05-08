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
  expansion: string;
};

type WeatherVariant = keyof typeof VARIANT_CLASSES;

export const VARIANT_CLASSES = {
  sky:     "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-sky-700 dark:text-sky-300",
  blue:    "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-blue-700 dark:text-blue-300",
  indigo:  "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-indigo-700 dark:text-indigo-300",
  stone:   "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-stone-700 dark:text-stone-300",
  rose:    "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-rose-700 dark:text-rose-300",
  emerald: "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-emerald-700 dark:text-emerald-300",
  green:   "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-green-700 dark:text-green-300",
  teal:    "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-teal-700 dark:text-teal-300",
  cyan:    "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-cyan-700 dark:text-cyan-300",
  amber:   "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-amber-700 dark:text-amber-300",
  slate:   "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-slate-700 dark:text-slate-300",
  orange:  "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-orange-700 dark:text-orange-300",
  violet:  "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-violet-700 dark:text-violet-300",
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
  return VARIANT_CLASSES[formatWeatherVariant(value)] ?? VARIANT_CLASSES[DEFAULT_VARIANT];
}

export function formatWeatherExpansion(value: WeatherAxisLabel): string | null {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.expansion;
  return null;
}

export function formatWeatherReadout(report: WeatherReport): string {
  return [
    formatWeatherLabel(report.truth.label),
    formatWeatherLabel(report.relevance.label),
    formatWeatherLabel(report.sentiment.label),
  ].join(" · ");
}
