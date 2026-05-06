import { describe, expect, it } from "vitest";
import { buildRollingOption } from "~/components/sidebar/reports/sentiment-timeline/buildRollingOption";
import type { SentimentBucket } from "~/lib/sentiment-buckets";

const BASE_MS = Date.UTC(2026, 0, 1, 9, 0, 0);

function formatWindow(startMs: number, endMs: number): string {
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return `${formatter.format(startMs)}-${formatter.format(endMs)}`;
}

function makeBuckets(): SentimentBucket[] {
  return [
    {
      startMs: BASE_MS,
      endMs: BASE_MS + 15 * 60_000,
      counts: { positive: 2, negative: 1, neutral: 1 },
      runningPct: { positive: 50, negative: 25, neutral: 25 },
    },
    {
      startMs: BASE_MS + 15 * 60_000,
      endMs: BASE_MS + 30 * 60_000,
      counts: { positive: 1, negative: 2, neutral: 1 },
      runningPct: { positive: 37.5, negative: 37.5, neutral: 25 },
    },
  ];
}

describe("buildRollingOption", () => {
  it("builds three stacked bar series with bucket-bound time-axis limits", () => {
    const buckets = makeBuckets();
    const option = buildRollingOption(buckets);
    const series = Array.isArray(option.series) ? option.series : [];

    expect(series).toHaveLength(3);
    expect(
      series.map((entry) => ({
        name: entry.name,
        type: entry.type,
        stack: entry.stack,
      })),
    ).toEqual([
      { name: "Positive", type: "bar", stack: "sentiment" },
      { name: "Negative", type: "bar", stack: "sentiment" },
      { name: "Neutral", type: "bar", stack: "sentiment" },
    ]);

    expect(option.xAxis).toMatchObject({
      type: "time",
      min: buckets[0].startMs,
      max: buckets[buckets.length - 1].endMs,
    });
    expect(option.yAxis).toMatchObject({
      type: "value",
      min: 0,
      max: 100,
    });
  });

  it("formats tooltip windows in local time with one-decimal running percentages", () => {
    const option = buildRollingOption(makeBuckets());
    const tooltip = option.tooltip;

    expect(tooltip).toBeDefined();
    expect(tooltip?.trigger).toBe("axis");
    expect(typeof tooltip?.formatter).toBe("function");

    const text = (tooltip!.formatter as (params: unknown) => string)([
      {
        axisValue: BASE_MS + 15 * 60_000,
        data: [BASE_MS + 15 * 60_000, 37.5],
        seriesName: "Positive",
      },
      {
        axisValue: BASE_MS + 15 * 60_000,
        data: [BASE_MS + 15 * 60_000, 37.5],
        seriesName: "Negative",
      },
      {
        axisValue: BASE_MS + 15 * 60_000,
        data: [BASE_MS + 15 * 60_000, 25],
        seriesName: "Neutral",
      },
    ]);

    expect(text).toContain(
      formatWindow(BASE_MS + 15 * 60_000, BASE_MS + 30 * 60_000),
    );
    expect(text).toContain("Positive: 37.5%");
    expect(text).toContain("Negative: 37.5%");
    expect(text).toContain("Neutral: 25.0%");
  });
});
