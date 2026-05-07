import type { components } from "~/lib/generated-types";

type SentimentScore = components["schemas"]["SentimentScore"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];
type SentimentLabel = SentimentScore["label"];

export interface SentimentBucket {
  startMs: number;
  endMs: number;
  counts: { positive: number; negative: number; neutral: number };
  runningPct: { positive: number; negative: number; neutral: number };
}

export interface BucketResult {
  buckets: SentimentBucket[];
  coverage: number;
  renderable: boolean;
}

interface TimestampedScore {
  label: SentimentLabel;
  timestampMs: number;
}

const MIN_BUCKET_MS = 30 * 60 * 1000;
const TARGET_BUCKETS = 20;
const COVERAGE_THRESHOLD = 0.8;
const LABELS: SentimentLabel[] = ["positive", "negative", "neutral"];

function createEmptyCounts(): SentimentBucket["counts"] {
  return { positive: 0, negative: 0, neutral: 0 };
}

function toTimestampMs(timestamp?: string | null): number | null {
  if (!timestamp) {
    return null;
  }

  const parsed = Date.parse(timestamp);
  return Number.isFinite(parsed) ? parsed : null;
}

export function bucketSentimentByTime(
  scores: SentimentScore[],
  anchors: UtteranceAnchor[],
): BucketResult {
  if (scores.length === 0) {
    return { buckets: [], coverage: 0, renderable: false };
  }

  const timestampByUtteranceId = new Map<string, number>();
  for (const anchor of anchors) {
    const timestampMs = toTimestampMs(anchor.timestamp);
    if (timestampMs != null) {
      timestampByUtteranceId.set(anchor.utterance_id, timestampMs);
    }
  }

  const timestampedScores: TimestampedScore[] = [];
  for (const score of scores) {
    const timestampMs = timestampByUtteranceId.get(score.utterance_id);
    if (timestampMs != null) {
      timestampedScores.push({ label: score.label, timestampMs });
    }
  }

  const coverage = timestampedScores.length / scores.length;
  if (timestampedScores.length === 0) {
    return { buckets: [], coverage, renderable: false };
  }

  let minMs = timestampedScores[0].timestampMs;
  let maxMs = timestampedScores[0].timestampMs;
  for (const score of timestampedScores) {
    if (score.timestampMs < minMs) minMs = score.timestampMs;
    if (score.timestampMs > maxMs) maxMs = score.timestampMs;
  }

  const totalRange = maxMs - minMs;
  const bucketSize =
    totalRange === 0
      ? MIN_BUCKET_MS
      : Math.max(MIN_BUCKET_MS, Math.ceil(totalRange / TARGET_BUCKETS));
  const bucketCount =
    totalRange === 0
      ? 1
      : Math.min(TARGET_BUCKETS, Math.max(1, Math.ceil(totalRange / bucketSize)));

  const buckets: SentimentBucket[] = Array.from({ length: bucketCount }, (_, index) => {
    const startMs = minMs + index * bucketSize;
    const endMs =
      index === bucketCount - 1 ? maxMs : Math.min(maxMs, startMs + bucketSize);

    return {
      startMs,
      endMs,
      counts: createEmptyCounts(),
      runningPct: createEmptyCounts(),
    };
  });

  for (const score of timestampedScores) {
    const offset = score.timestampMs - minMs;
    const rawIndex = totalRange === 0 ? 0 : Math.floor(offset / bucketSize);
    const bucketIndex = Math.min(rawIndex, bucketCount - 1);
    buckets[bucketIndex].counts[score.label] += 1;
  }

  const runningCounts = createEmptyCounts();
  for (const bucket of buckets) {
    for (const label of LABELS) {
      runningCounts[label] += bucket.counts[label];
    }

    const cumulativeTotal =
      runningCounts.positive + runningCounts.negative + runningCounts.neutral;

    for (const label of LABELS) {
      bucket.runningPct[label] =
        cumulativeTotal === 0
          ? 0
          : (runningCounts[label] / cumulativeTotal) * 100;
    }
  }

  return {
    buckets,
    coverage,
    renderable: coverage >= COVERAGE_THRESHOLD && buckets.length >= 2,
  };
}
