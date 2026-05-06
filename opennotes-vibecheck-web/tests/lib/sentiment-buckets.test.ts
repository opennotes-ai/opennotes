import { describe, expect, it } from "vitest";
import { bucketSentimentByTime } from "~/lib/sentiment-buckets";
import type { components } from "~/lib/generated-types";

type SentimentScore = components["schemas"]["SentimentScore"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

const BASE_MS = Date.UTC(2026, 0, 1, 0, 0, 0);

function makeScore(
  utteranceId: string,
  label: SentimentScore["label"],
): SentimentScore {
  return {
    utterance_id: utteranceId,
    label,
    valence: label === "positive" ? 0.75 : label === "negative" ? -0.75 : 0,
  };
}

function makeAnchor(
  utteranceId: string,
  timestampMs?: number | null,
): UtteranceAnchor {
  return {
    position: 1,
    utterance_id: utteranceId,
    timestamp:
      timestampMs == null ? timestampMs ?? null : new Date(timestampMs).toISOString(),
  };
}

describe("bucketSentimentByTime", () => {
  it("returns empty buckets and non-renderable output for empty input", () => {
    expect(bucketSentimentByTime([], [])).toEqual({
      buckets: [],
      coverage: 0,
      renderable: false,
    });
  });

  it("returns a single non-renderable bucket for one timestamped score", () => {
    const result = bucketSentimentByTime(
      [makeScore("u-1", "positive")],
      [makeAnchor("u-1", BASE_MS)],
    );

    expect(result.coverage).toBe(1);
    expect(result.renderable).toBe(false);
    expect(result.buckets).toHaveLength(1);
    expect(result.buckets[0]).toEqual({
      startMs: BASE_MS,
      endMs: BASE_MS,
      counts: { positive: 1, negative: 0, neutral: 0 },
      runningPct: { positive: 100, negative: 0, neutral: 0 },
    });
  });

  it("returns empty buckets and zero coverage when every score is untimestamped", () => {
    const scores = [makeScore("u-1", "positive"), makeScore("u-2", "negative")];
    const anchors = [makeAnchor("u-1", null), makeAnchor("u-2", undefined)];

    expect(bucketSentimentByTime(scores, anchors)).toEqual({
      buckets: [],
      coverage: 0,
      renderable: false,
    });
  });

  it("is renderable at exactly 80% coverage when at least two buckets exist", () => {
    const scores = [
      makeScore("u-1", "positive"),
      makeScore("u-2", "negative"),
      makeScore("u-3", "neutral"),
      makeScore("u-4", "positive"),
      makeScore("u-5", "negative"),
    ];
    const anchors = [
      makeAnchor("u-1", BASE_MS),
      makeAnchor("u-2", BASE_MS + 10 * 60_000),
      makeAnchor("u-3", BASE_MS + 31 * 60_000),
      makeAnchor("u-4", BASE_MS + 61 * 60_000),
      makeAnchor("u-5", null),
    ];

    const result = bucketSentimentByTime(scores, anchors);

    expect(result.coverage).toBe(0.8);
    expect(result.buckets.length).toBeGreaterThanOrEqual(2);
    expect(result.renderable).toBe(true);
  });

  it("is not renderable just below 80% coverage", () => {
    const scores = Array.from({ length: 9 }, (_, index) =>
      makeScore(`u-${index + 1}`, index % 3 === 0 ? "positive" : index % 3 === 1 ? "negative" : "neutral"),
    );
    const anchors = [
      makeAnchor("u-1", BASE_MS),
      makeAnchor("u-2", BASE_MS + 5 * 60_000),
      makeAnchor("u-3", BASE_MS + 10 * 60_000),
      makeAnchor("u-4", BASE_MS + 35 * 60_000),
      makeAnchor("u-5", BASE_MS + 40 * 60_000),
      makeAnchor("u-6", BASE_MS + 45 * 60_000),
      makeAnchor("u-7", BASE_MS + 70 * 60_000),
      makeAnchor("u-8", null),
      makeAnchor("u-9", undefined),
    ];

    const result = bucketSentimentByTime(scores, anchors);

    expect(result.coverage).toBeCloseTo(7 / 9, 10);
    expect(result.buckets.length).toBeGreaterThanOrEqual(2);
    expect(result.renderable).toBe(false);
  });

  it("collapses a total range under 30 minutes into one bucket", () => {
    const result = bucketSentimentByTime(
      [makeScore("u-1", "positive"), makeScore("u-2", "negative")],
      [makeAnchor("u-1", BASE_MS), makeAnchor("u-2", BASE_MS + 29 * 60_000)],
    );

    expect(result.buckets).toHaveLength(1);
    expect(result.renderable).toBe(false);
  });

  it("uses exactly 20 buckets across a 24-hour range and includes boundary timestamps", () => {
    const scores = [
      makeScore("u-1", "positive"),
      makeScore("u-2", "negative"),
      makeScore("u-3", "neutral"),
      makeScore("u-4", "positive"),
    ];
    const anchors = [
      makeAnchor("u-1", BASE_MS),
      makeAnchor("u-2", BASE_MS + 6 * 60 * 60_000),
      makeAnchor("u-3", BASE_MS + 12 * 60 * 60_000),
      makeAnchor("u-4", BASE_MS + 24 * 60 * 60_000),
    ];

    const result = bucketSentimentByTime(scores, anchors);
    const firstBucket = result.buckets[0];
    const lastBucket = result.buckets[result.buckets.length - 1];

    expect(result.coverage).toBe(1);
    expect(result.buckets).toHaveLength(20);
    expect(firstBucket?.counts).toEqual({
      positive: 1,
      negative: 0,
      neutral: 0,
    });
    expect(lastBucket?.counts).toEqual({
      positive: 1,
      negative: 0,
      neutral: 0,
    });
  });

  it("sets the last running percentages to the global sentiment breakdown", () => {
    const scores = [
      makeScore("u-1", "positive"),
      makeScore("u-2", "negative"),
      makeScore("u-3", "neutral"),
      makeScore("u-4", "positive"),
    ];
    const anchors = [
      makeAnchor("u-1", BASE_MS),
      makeAnchor("u-2", BASE_MS + 31 * 60_000),
      makeAnchor("u-3", BASE_MS + 62 * 60_000),
      makeAnchor("u-4", BASE_MS + 93 * 60_000),
    ];

    const result = bucketSentimentByTime(scores, anchors);
    const lastBucket = result.buckets[result.buckets.length - 1];
    const runningTotal =
      lastBucket.runningPct.positive +
      lastBucket.runningPct.negative +
      lastBucket.runningPct.neutral;

    expect(lastBucket.runningPct).toEqual({
      positive: 50,
      negative: 25,
      neutral: 25,
    });
    expect(runningTotal).toBeCloseTo(100, 10);
  });

  it("keeps each non-empty running percentage total within a tight 100% tolerance", () => {
    const scores = [
      makeScore("u-1", "positive"),
      makeScore("u-2", "negative"),
      makeScore("u-3", "neutral"),
      makeScore("u-4", "positive"),
    ];
    const anchors = [
      makeAnchor("u-1", BASE_MS),
      makeAnchor("u-2", BASE_MS + 31 * 60_000),
      makeAnchor("u-3", BASE_MS + 62 * 60_000),
      makeAnchor("u-4", BASE_MS + 93 * 60_000),
    ];

    const result = bucketSentimentByTime(scores, anchors);

    for (const bucket of result.buckets) {
      const total =
        bucket.runningPct.positive +
        bucket.runningPct.negative +
        bucket.runningPct.neutral;

      expect(total).toBeCloseTo(100, 10);
    }
  });
});
