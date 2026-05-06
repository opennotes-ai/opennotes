import type { EChartsOption } from "echarts";
import type { SentimentBucket } from "~/lib/sentiment-buckets";

type SentimentKey = keyof SentimentBucket["counts"];
type SentimentLabel = "Positive" | "Neutral" | "Negative";
type ScatterDatum = [number, SentimentLabel, number];

const SENTIMENTS: Array<{
  key: SentimentKey;
  label: SentimentLabel;
  color: string;
}> = [
  { key: "positive", label: "Positive", color: "oklch(0.65 0.15 165)" },
  { key: "neutral", label: "Neutral", color: "oklch(0.50 0.01 160 / 0.4)" },
  { key: "negative", label: "Negative", color: "oklch(0.577 0.245 27.325)" },
];

function midpointMs(bucket: SentimentBucket): number {
  return bucket.startMs + (bucket.endMs - bucket.startMs) / 2;
}

function formatUtcTimestamp(timestampMs: number): string {
  const iso = new Date(timestampMs).toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

function formatBucketWindow(bucket: SentimentBucket): string {
  return `${formatUtcTimestamp(bucket.startMs)} - ${formatUtcTimestamp(bucket.endMs)}`;
}

function getCount(value: unknown): number {
  if (!Array.isArray(value) || value.length < 3) {
    return 0;
  }

  const rawCount = value[2];
  return typeof rawCount === "number" && Number.isFinite(rawCount) ? rawCount : 0;
}

export function buildPunchCardOption(buckets: SentimentBucket[]): EChartsOption {
  const maxCount = buckets.reduce((largest, bucket) => {
    const bucketMax = Math.max(
      bucket.counts.positive,
      bucket.counts.neutral,
      bucket.counts.negative,
    );
    return Math.max(largest, bucketMax);
  }, 0);

  const bucketByMidpoint = new Map<number, SentimentBucket>(
    buckets.map((bucket) => [midpointMs(bucket), bucket]),
  );

  const symbolSize = (value: unknown): number => {
    const count = getCount(value);
    if (count <= 0) {
      return 0;
    }
    if (maxCount <= 0) {
      return 0;
    }

    const normalized = Math.sqrt(count) / Math.sqrt(maxCount);
    return Math.max(4, Math.min(24, 4 + normalized * 20));
  };

  const series = SENTIMENTS.map(({ key, label, color }) => ({
    name: label,
    type: "scatter" as const,
    itemStyle: { color },
    symbolSize,
    data: buckets.map((bucket): ScatterDatum => [
      midpointMs(bucket),
      label,
      bucket.counts[key],
    ]),
  }));

  return {
    animation: false,
    grid: { top: 8, right: 8, bottom: 24, left: 64 },
    xAxis: {
      type: "time",
      min: buckets[0]?.startMs,
      max: buckets[buckets.length - 1]?.endMs,
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: SENTIMENTS.map((entry) => entry.label),
    },
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        const point = Array.isArray(params) ? params[0] : params;
        const datum = Array.isArray(point?.data) ? point.data : null;
        const midpoint = typeof datum?.[0] === "number" ? datum[0] : null;
        const bucket = midpoint != null ? bucketByMidpoint.get(midpoint) : undefined;
        if (!bucket) {
          return "";
        }

        return [
          formatBucketWindow(bucket),
          `Positive: ${bucket.counts.positive}`,
          `Neutral: ${bucket.counts.neutral}`,
          `Negative: ${bucket.counts.negative}`,
        ].join("<br/>");
      },
    },
    series,
  };
}
