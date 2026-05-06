import { describe, expect, it } from "vitest";
import type { EChartsOption } from "echarts";
import type { SentimentBucket } from "../../../../../src/lib/sentiment-buckets";
import { buildPunchCardOption } from "../../../../../src/components/sidebar/reports/sentiment-timeline/buildPunchCardOption";

type ScatterDatum = [number, "Positive" | "Neutral" | "Negative", number];

function makeBuckets(): SentimentBucket[] {
  return [
    {
      startMs: Date.UTC(2026, 4, 6, 12, 0, 0),
      endMs: Date.UTC(2026, 4, 6, 12, 30, 0),
      counts: { positive: 5, neutral: 2, negative: 3 },
      runningPct: { positive: 50, neutral: 20, negative: 30 },
    },
    {
      startMs: Date.UTC(2026, 4, 6, 12, 30, 0),
      endMs: Date.UTC(2026, 4, 6, 13, 0, 0),
      counts: { positive: 0, neutral: 0, negative: 0 },
      runningPct: { positive: 50, neutral: 20, negative: 30 },
    },
    {
      startMs: Date.UTC(2026, 4, 6, 13, 0, 0),
      endMs: Date.UTC(2026, 4, 6, 13, 30, 0),
      counts: { positive: 1, neutral: 0, negative: 7 },
      runningPct: { positive: 40, neutral: 15, negative: 45 },
    },
  ];
}

function asOption(): EChartsOption {
  return buildPunchCardOption(makeBuckets());
}

describe("buildPunchCardOption", () => {
  it("builds three scatter series with sentiment categories in visible display order", () => {
    const option = asOption();
    const series = option.series as Array<{ type?: string; data?: ScatterDatum[] }>;
    const yAxis = option.yAxis as {
      type?: string;
      data?: string[];
      inverse?: boolean;
    };

    expect(yAxis.type).toBe("category");
    expect(yAxis.inverse).toBe(true);
    expect(yAxis.data).toEqual(["Positive", "Neutral", "Negative"]);
    expect(series).toHaveLength(3);
    expect(series.map((entry) => entry.type)).toEqual([
      "scatter",
      "scatter",
      "scatter",
    ]);
    expect(series[0]?.data?.[0]).toEqual([
      Date.UTC(2026, 4, 6, 12, 15, 0),
      "Positive",
      5,
    ]);
  });

  it("uses the same x-axis bounds as the bucket range and hides zero-count cells", () => {
    const option = asOption();
    const xAxis = option.xAxis as { min?: number; max?: number };
    const series = option.series as Array<{
      itemStyle?: { color?: string };
      symbolSize?: (value: ScatterDatum) => number;
    }>;

    expect(xAxis.min).toBe(Date.UTC(2026, 4, 6, 12, 0, 0));
    expect(xAxis.max).toBe(Date.UTC(2026, 4, 6, 13, 30, 0));

    const symbolSize = series[0]?.symbolSize;
    expect(symbolSize).toBeTypeOf("function");
    expect(symbolSize?.([Date.UTC(2026, 4, 6, 12, 45, 0), "Positive", 0])).toBe(0);

    const positiveSize = symbolSize?.([Date.UTC(2026, 4, 6, 12, 15, 0), "Positive", 5]);
    expect(positiveSize).toBeGreaterThan(0);
    expect(positiveSize).toBeLessThanOrEqual(24);
    expect(series[1]?.itemStyle?.color).toBe("oklch(0.50 0.01 160 / 0.4)");
  });

  it("formats the tooltip with bucket window and per-sentiment counts", () => {
    const option = asOption();
    const tooltip = option.tooltip as {
      formatter?: (params: { data: ScatterDatum }) => string;
    };

    expect(tooltip.formatter).toBeTypeOf("function");

    const text = tooltip.formatter?.({
      data: [Date.UTC(2026, 4, 6, 12, 15, 0), "Positive", 5],
    });

    expect(text).toContain("2026-05-06 12:00 UTC");
    expect(text).toContain("2026-05-06 12:30 UTC");
    expect(text).toContain("Positive: 5");
    expect(text).toContain("Neutral: 2");
    expect(text).toContain("Negative: 3");
  });
});
