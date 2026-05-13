import { describe, expect, it } from "vitest";
import type { EChartsOption } from "echarts";
import { buildRollingOption } from "./buildRollingOption";
import type { SentimentBucket } from "~/lib/sentiment-buckets";

function makeBucket(startMs: number, endMs: number): SentimentBucket {
  return {
    startMs,
    endMs,
    counts: { positive: 1, negative: 1, neutral: 1 },
    runningPct: { positive: 33, negative: 33, neutral: 34 },
  };
}

function getFormatter(option: EChartsOption): (value: number) => string {
  const xAxis = Array.isArray(option.xAxis) ? option.xAxis[0] : option.xAxis;
  const formatter = (xAxis as { axisLabel?: { formatter?: (v: number) => string } })
    ?.axisLabel?.formatter;
  if (typeof formatter !== "function") {
    throw new Error("axisLabel.formatter is not a function");
  }
  return formatter;
}

describe("buildRollingOption", () => {
  describe("grid alignment", () => {
    it("hides y-axis labels and uses left margin of 64 to align with punch card chart", () => {
      const start = new Date("2026-05-06T10:00:00Z").getTime();
      const end = new Date("2026-05-06T14:00:00Z").getTime();
      const option = buildRollingOption([makeBucket(start, end)]);

      const grid = Array.isArray(option.grid) ? option.grid[0] : option.grid;
      expect((grid as { left?: number })?.left).toBe(64);

      const yAxis = Array.isArray(option.yAxis) ? option.yAxis[0] : option.yAxis;
      const yConfig = yAxis as { axisLabel?: { show?: boolean }; axisTick?: { show?: boolean }; axisLine?: { show?: boolean } };
      expect(yConfig?.axisLabel?.show).toBe(false);
      expect(yConfig?.axisTick?.show).toBe(false);
      expect(yConfig?.axisLine?.show).toBe(false);
    });
  });

  describe("single-day job", () => {
    it("formats x-axis ticks as HH:MM only", () => {
      const dayStart = new Date("2026-05-06T10:00:00Z").getTime();
      const dayEnd = new Date("2026-05-06T14:00:00Z").getTime();
      const mid = new Date("2026-05-06T12:00:00Z").getTime();

      const buckets = [makeBucket(dayStart, mid), makeBucket(mid, dayEnd)];
      const option = buildRollingOption(buckets);
      const formatter = getFormatter(option);

      const result = formatter(dayStart);
      expect(result).toMatch(/^\d{2}:\d{2}$/);
    });
  });

  describe("multi-day job", () => {
    it("includes the date for ticks on day A and day B", () => {
      const dayAStart = new Date("2026-05-06T20:00:00").getTime();
      const dayAEnd = new Date("2026-05-06T23:59:59").getTime();
      const dayBStart = new Date("2026-05-07T00:00:00").getTime();
      const dayBEnd = new Date("2026-05-07T12:00:00").getTime();

      const buckets = [
        makeBucket(dayAStart, dayAEnd),
        makeBucket(dayBStart, dayBEnd),
      ];
      const option = buildRollingOption(buckets);
      const formatter = getFormatter(option);

      const dayALabel = formatter(dayAStart);
      const dayBLabel = formatter(dayBStart);

      expect(dayALabel).toMatch(/May\s+6/i);
      expect(dayBLabel).toMatch(/May\s+7/i);
    });
  });
});
