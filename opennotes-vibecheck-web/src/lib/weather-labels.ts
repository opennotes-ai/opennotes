import type { components } from "~/lib/generated-types";

type WeatherReport = components["schemas"]["WeatherReport"];
type WeatherAxisLabel =
  | WeatherReport["truth"]["label"]
  | WeatherReport["relevance"]["label"]
  | WeatherReport["sentiment"]["label"];

export function formatWeatherLabel(value: WeatherAxisLabel): string {
  switch (value) {
    case "mostly_factual":
      return "Mostly Factual";
    case "self_reported":
      return "Self-Reported";
    case "on_topic":
      return "On Topic";
    case "off_topic":
      return "Off Topic";
    default:
      return String(value)
        .split(/[_\s-]+/)
        .filter(Boolean)
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(" ");
  }
}

export function formatWeatherReadout(report: WeatherReport): string {
  return [
    formatWeatherLabel(report.truth.label),
    formatWeatherLabel(report.relevance.label),
    formatWeatherLabel(report.sentiment.label),
  ].join(" · ");
}
