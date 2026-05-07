import type { components } from "~/lib/generated-types";

type WeatherReport = components["schemas"]["WeatherReport"];
type WeatherAxisLabel =
  | WeatherReport["truth"]["label"]
  | WeatherReport["relevance"]["label"]
  | WeatherReport["sentiment"]["label"];

export function formatWeatherLabel(value: WeatherAxisLabel): string {
  switch (value) {
    case "sourced":
      return "Sourced";
    case "factual_claims":
      return "Factual claims";
    case "first_person":
      return "First-person";
    case "hearsay":
      return "Second-hand";
    case "misleading":
      return "Actively misleading";
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
