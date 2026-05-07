import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import WeatherReport from "./WeatherReport";

type WeatherReportData = components["schemas"]["WeatherReport"];

function makeWeatherReport(
  overrides: Partial<WeatherReportData> = {},
): WeatherReportData {
  return {
    truth: {
      label: "self_reported",
      logprob: null,
      alternatives: [],
    },
    relevance: {
      label: "on_topic",
      logprob: null,
      alternatives: [],
    },
    sentiment: {
      label: "warmly skeptical",
      logprob: null,
      alternatives: [],
    },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("WeatherReport", () => {
  it("renders truth, relevance, and sentiment evaluations", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    expect(screen.getByTestId("weather-axis-card-truth")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-relevance")).toBeDefined();
    expect(screen.getByTestId("weather-axis-card-sentiment")).toBeDefined();
    expect(screen.getByTestId("weather-truth-value").textContent).toBe(
      "Self-reported",
    );
    expect(screen.getByTestId("weather-relevance-value").textContent).toBe(
      "On topic",
    );
    expect(screen.getByTestId("weather-sentiment-value").textContent).toBe(
      "warmly skeptical",
    );
  });

  it("renders stable extra-shimmery skeletons when report is null", () => {
    render(() => <WeatherReport report={null} />);

    expect(screen.getByTestId("weather-report-skeleton")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-truth")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-relevance")).toBeDefined();
    expect(screen.getByTestId("weather-skeleton-sentiment")).toBeDefined();
    expect(
      screen
        .getByTestId("weather-skeleton-truth")
        .querySelector(".skeleton-pulse-extra"),
    ).toBeTruthy();
  });

  it("keeps self-reported truth neutral, not amber or destructive", () => {
    render(() => <WeatherReport report={makeWeatherReport()} />);

    const className = screen.getByTestId("weather-truth-value").className;
    expect(className).toContain("text-muted-foreground");
    expect(className).not.toContain("amber");
    expect(className).not.toContain("destructive");
  });

  it("uses a horizontal row by default and accepts desktop rail classes", () => {
    render(() => (
      <WeatherReport report={makeWeatherReport()} class="grid-cols-3 lg:grid-cols-1" />
    ));

    const className = screen.getByTestId("weather-report").className;
    expect(className).toContain("grid-cols-3");
    expect(className).toContain("lg:grid-cols-1");
  });

  it("renders alternatives only when present", () => {
    render(() => (
      <WeatherReport
        report={makeWeatherReport({
          truth: {
            label: "sourced",
            logprob: null,
            alternatives: [{ label: "mostly_factual", logprob: null }],
          },
        })}
      />
    ));

    expect(screen.getByTestId("weather-truth-alternatives")).toBeDefined();
    expect(screen.queryByTestId("weather-relevance-alternatives")).toBeNull();
  });
});
