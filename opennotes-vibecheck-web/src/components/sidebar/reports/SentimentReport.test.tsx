import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import SentimentReport from "./SentimentReport";

type SentimentStatsReport = components["schemas"]["SentimentStatsReport"];

afterEach(() => {
  cleanup();
});

function makeSentimentStats(
  overrides: Partial<SentimentStatsReport> = {},
): SentimentStatsReport {
  return {
    positive_pct: 42,
    negative_pct: 27,
    neutral_pct: 31,
    mean_valence: 0.08,
    per_utterance: [],
    ...overrides,
  };
}

describe("SentimentReport", () => {
  it("renders percentage shares without leading plus or minus signs", () => {
    render(() => <SentimentReport stats={makeSentimentStats()} />);

    expect(screen.getByTestId("sentiment-positive-label").textContent).toBe("42%");
    expect(screen.getByTestId("sentiment-negative-label").textContent).toBe("27%");
    expect(screen.getByTestId("sentiment-positive-label").textContent).not.toContain("+");
    expect(screen.getByTestId("sentiment-negative-label").textContent).not.toContain("-");
  });

  it("uses semantic color classes for sentiment bars", () => {
    render(() => <SentimentReport stats={makeSentimentStats()} />);

    expect(screen.getByTestId("sentiment-positive").className).toContain(
      "bg-positive",
    );
    expect(screen.getByTestId("sentiment-negative").className).toContain(
      "bg-negative",
    );
    expect(screen.getByTestId("sentiment-neutral").className).toContain(
      "bg-muted-foreground/40",
    );
  });

  it("uses semantic label colors and centered fixed columns", () => {
    render(() => <SentimentReport stats={makeSentimentStats()} />);

    const legend = screen.getByTestId("sentiment-legend");
    expect(legend.className).toContain("grid-cols-3");
    expect(legend.className).toContain("justify-items-center");

    const positiveLabel = screen.getByTestId("sentiment-positive-label");
    const negativeLabel = screen.getByTestId("sentiment-negative-label");

    expect(positiveLabel.className).toContain("text-positive");
    expect(negativeLabel.className).toContain("text-negative");
  });
});
