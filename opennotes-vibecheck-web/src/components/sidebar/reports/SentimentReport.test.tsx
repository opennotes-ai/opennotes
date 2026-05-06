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

  function widthAsNumber(el: HTMLElement): number {
    const raw = el.style.width;
    const match = /^([\d.]+)%$/.exec(raw);
    expect(match, `expected width style to be a percentage, got "${raw}"`).not.toBeNull();
    return Number(match![1]);
  }

  it("renormalizes overflowing percentages so segments fit and labels stay consistent", () => {
    render(() => (
      <SentimentReport
        stats={makeSentimentStats({
          positive_pct: 60,
          negative_pct: 60,
          neutral_pct: 20,
        })}
      />
    ));

    const positiveBar = screen.getByTestId("sentiment-positive");
    const negativeBar = screen.getByTestId("sentiment-negative");
    const neutralBar = screen.getByTestId("sentiment-neutral");
    const sum =
      widthAsNumber(positiveBar) +
      widthAsNumber(negativeBar) +
      widthAsNumber(neutralBar);
    expect(sum).toBeLessThanOrEqual(100);

    const positiveLabel = screen.getByTestId("sentiment-positive-label").textContent;
    const negativeLabel = screen.getByTestId("sentiment-negative-label").textContent;
    const neutralLabel = screen.getByTestId("sentiment-neutral-label").textContent;
    expect(positiveLabel).toBe(`${widthAsNumber(positiveBar)}%`);
    expect(negativeLabel).toBe(`${widthAsNumber(negativeBar)}%`);
    expect(neutralLabel).toBe(`${widthAsNumber(neutralBar)}%`);

    const wrapper = screen.getByLabelText(
      `Sentiment: ${widthAsNumber(positiveBar)}% positive, ${widthAsNumber(negativeBar)}% negative, ${widthAsNumber(neutralBar)}% neutral`,
    );
    expect(wrapper).toBeDefined();

    expect(positiveBar.className).toContain("bg-positive");
    expect(negativeBar.className).toContain("bg-negative");
    expect(neutralBar.className).toContain("bg-muted-foreground/40");
  });

  it("leaves percentages untouched when the total is already at or below 100", () => {
    render(() => (
      <SentimentReport
        stats={makeSentimentStats({
          positive_pct: 50,
          negative_pct: 30,
          neutral_pct: 20,
        })}
      />
    ));

    expect(screen.getByTestId("sentiment-positive-label").textContent).toBe("50%");
    expect(screen.getByTestId("sentiment-negative-label").textContent).toBe("30%");
    expect(screen.getByTestId("sentiment-neutral-label").textContent).toBe("20%");
    expect(screen.getByTestId("sentiment-positive").style.width).toBe("50%");
    expect(screen.getByTestId("sentiment-negative").style.width).toBe("30%");
    expect(screen.getByTestId("sentiment-neutral").style.width).toBe("20%");
  });
});
