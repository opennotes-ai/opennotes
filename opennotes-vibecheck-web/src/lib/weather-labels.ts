import type { components } from "~/lib/generated-types";
import weatherLabelsJson from "./weather-labels.json";

type WeatherReport = components["schemas"]["WeatherReport"];
type WeatherAxisLabel =
  | WeatherReport["truth"]["label"]
  | WeatherReport["relevance"]["label"]
  | WeatherReport["sentiment"]["label"];

type WeatherLabelEntry = {
  axis: "truth" | "relevance" | "sentiment" | "safety";
  label: string;
  variant: WeatherVariant;
  expansion: string;
};

type WeatherVariant = keyof typeof VARIANT_CLASSES;

export const VARIANT_CLASSES = {
  sky:          "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-sky-700 dark:text-sky-300",
  indigo:       "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-indigo-700 dark:text-indigo-300",
  stone:        "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-stone-700 dark:text-stone-300",
  emerald:      "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-emerald-700 dark:text-emerald-300",
  teal:         "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-teal-700 dark:text-teal-300",
  cyan:         "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-cyan-700 dark:text-cyan-300",
  lime:         "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-lime-700 dark:text-lime-300",
  fuchsia:      "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-fuchsia-700 dark:text-fuchsia-300",
  amber:        "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-amber-700 dark:text-amber-300",
  slate:        "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-slate-700 dark:text-slate-300",
  orange:       "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-orange-700 dark:text-orange-300",
  violet:       "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-violet-700 dark:text-violet-300",
  "emerald-soft": "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-emerald-800 dark:text-emerald-300 bg-emerald-100/70 dark:bg-emerald-900/30",
  yellow:       "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-yellow-800 dark:text-yellow-300 bg-yellow-100/70 dark:bg-yellow-900/30",
  "amber-strong": "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-amber-800 dark:text-amber-300 bg-amber-100/80 dark:bg-amber-900/40",
  "rose-strong":  "inline-flex rounded-md px-2 py-1 text-lg font-semibold text-rose-50 bg-rose-700 dark:bg-rose-600",
} as const satisfies Record<string, string>;

export type AxisType = "truth" | "relevance" | "sentiment" | "safety";

export type AxisDefinition = {
  heading: string;
  description: string;
};

type VariantHexMap = Record<WeatherVariant, string>;

type _VariantHexExhaustive =
  keyof typeof weatherLabelsJson.variant_hex_colors extends WeatherVariant
    ? WeatherVariant extends keyof typeof weatherLabelsJson.variant_hex_colors
      ? true
      : never
    : never;
const _variantHexExhaustive: _VariantHexExhaustive = true;

export const VARIANT_HEX: VariantHexMap =
  weatherLabelsJson.variant_hex_colors as VariantHexMap;

type _AxisDefinitionsExhaustive =
  keyof typeof weatherLabelsJson.axis_definitions extends AxisType
    ? AxisType extends keyof typeof weatherLabelsJson.axis_definitions
      ? true
      : never
    : never;
const _axisDefinitionsExhaustive: _AxisDefinitionsExhaustive = true;

export const AXIS_DEFINITIONS: Record<AxisType, AxisDefinition> =
  weatherLabelsJson.axis_definitions as Record<AxisType, AxisDefinition>;

const DEFAULT_VARIANT: WeatherVariant = "slate";

const WEATHER_LABELS = weatherLabelsJson as unknown as Record<string, WeatherLabelEntry>;

function defaultTitleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function formatWeatherLabel(value: WeatherAxisLabel | string): string {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.label;
  return defaultTitleCase(String(value));
}

export function formatWeatherVariant(value: WeatherAxisLabel | string): WeatherVariant {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.variant;
  return DEFAULT_VARIANT;
}

export function formatWeatherExpansion(value: WeatherAxisLabel | string): string | null {
  const entry = WEATHER_LABELS[value as string];
  if (entry) return entry.expansion;
  return null;
}

export function getVariantHex(variant: WeatherVariant): string {
  return VARIANT_HEX[variant] ?? "#64748b";
}

export function getAxisDefinition(axis: AxisType): AxisDefinition {
  return AXIS_DEFINITIONS[axis];
}

export const VARIANT_TEXT_CLASSES = {
  sky:            "text-sky-700 dark:text-sky-300",
  indigo:         "text-indigo-700 dark:text-indigo-300",
  stone:          "text-stone-700 dark:text-stone-300",
  emerald:        "text-emerald-700 dark:text-emerald-300",
  teal:           "text-teal-700 dark:text-teal-300",
  cyan:           "text-cyan-700 dark:text-cyan-300",
  lime:           "text-lime-700 dark:text-lime-300",
  fuchsia:        "text-fuchsia-700 dark:text-fuchsia-300",
  amber:          "text-amber-700 dark:text-amber-300",
  slate:          "text-slate-700 dark:text-slate-300",
  orange:         "text-orange-700 dark:text-orange-300",
  violet:         "text-violet-700 dark:text-violet-300",
  "emerald-soft": "text-emerald-700 dark:text-emerald-300",
  yellow:         "text-yellow-700 dark:text-yellow-300",
  "amber-strong": "text-amber-700 dark:text-amber-300",
  "rose-strong":  "text-rose-700 dark:text-rose-300",
} as const satisfies Record<WeatherVariant, string>;

export function formatWeatherTextClass(value: WeatherAxisLabel | string): string {
  return VARIANT_TEXT_CLASSES[formatWeatherVariant(value)] ?? VARIANT_TEXT_CLASSES[DEFAULT_VARIANT];
}

export function formatWeatherReadout(report: WeatherReport): string {
  return [
    formatWeatherLabel(report.truth.label),
    formatWeatherLabel(report.relevance.label),
    formatWeatherLabel(report.sentiment.label),
  ].join(" · ");
}
