import type { components } from "~/lib/generated-types";
import type { SafetyLevel } from "~/components/sidebar/reports/WeatherSymbol";
import { formatWeatherVariant, getVariantHex } from "~/lib/weather-labels";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WeatherReport = components["schemas"]["WeatherReport"];

export function safetyLevel(rec: SafetyRecommendation | null | undefined): SafetyLevel {
  const level = rec?.level;
  if (level === "safe" || level === "mild" || level === "caution" || level === "unsafe") {
    return level;
  }
  return "unknown";
}

function variantHex(label: string): string {
  const variant = formatWeatherVariant(label);
  return getVariantHex(variant);
}

export function lobeColors(report: WeatherReport): [string, string, string] {
  return [
    variantHex(report.truth?.label ?? ""),
    variantHex(report.relevance?.label ?? ""),
    variantHex(report.sentiment?.label ?? ""),
  ];
}
