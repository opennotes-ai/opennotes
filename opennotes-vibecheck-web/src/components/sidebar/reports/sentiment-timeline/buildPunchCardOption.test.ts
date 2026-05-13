import { describe, expect, it } from "vitest";
import { buildPunchCardOption } from "./buildPunchCardOption";
import type { SentimentBucket } from "~/lib/sentiment-buckets";

function makeBucket(startMs: number, endMs: number): SentimentBucket {
  return {
    startMs,
    endMs,
    counts: { positive: 1, negative: 1, neutral: 1 },
    runningPct: { positive: 33, negative: 33, neutral: 34 },
  };
}

describe("buildPunchCardOption", () => {
  describe("grid alignment", () => {
    it("uses left margin of 64 to align with rolling chart", () => {
      const start = new Date("2026-05-06T10:00:00Z").getTime();
      const end = new Date("2026-05-06T14:00:00Z").getTime();
      const option = buildPunchCardOption([makeBucket(start, end)]);

      const grid = Array.isArray(option.grid) ? option.grid[0] : option.grid;
      expect((grid as { left?: number })?.left).toBe(64);
    });
  });
});
