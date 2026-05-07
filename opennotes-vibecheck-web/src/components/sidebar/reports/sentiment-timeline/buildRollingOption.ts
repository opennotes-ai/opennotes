import type { EChartsOption } from "echarts";
import type { SentimentBucket } from "~/lib/sentiment-buckets";

const POSITIVE_COLOR = "oklch(0.65 0.15 165)";
const NEGATIVE_COLOR = "oklch(0.577 0.245 27.325)";
const NEUTRAL_COLOR = "oklch(0.50 0.01 160 / 0.4)";

type SentimentKey = keyof SentimentBucket["runningPct"];

const SERIES_META: Array<{
  key: SentimentKey;
  name: string;
  color: string;
}> = [
  { key: "positive", name: "Positive", color: POSITIVE_COLOR },
  { key: "negative", name: "Negative", color: NEGATIVE_COLOR },
  { key: "neutral", name: "Neutral", color: NEUTRAL_COLOR },
];

function formatWindow(startMs: number, endMs: number): string {
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return `${formatter.format(startMs)}-${formatter.format(endMs)}`;
}

function formatTooltipValue(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0.0%";
  }

  return `${value.toFixed(1)}%`;
}

function normalizeParams(params: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(params)) {
    return params.filter(
      (entry): entry is Record<string, unknown> =>
        entry != null && typeof entry === "object",
    );
  }

  if (params != null && typeof params === "object") {
    return [params as Record<string, unknown>];
  }

  return [];
}

export function buildRollingOption(buckets: SentimentBucket[]): EChartsOption {
  const firstBucket = buckets[0];
  const lastBucket = buckets[buckets.length - 1];
  const bucketByStartMs = new Map(buckets.map((bucket) => [bucket.startMs, bucket]));

  return {
    grid: { top: 8, right: 8, bottom: 24, left: 32 },
    tooltip: {
      trigger: "axis",
      formatter: (rawParams) => {
        const params = normalizeParams(rawParams);
        const axisValue = params[0]?.axisValue;
        const startMs =
          typeof axisValue === "number"
            ? axisValue
            : typeof axisValue === "string"
              ? Number(axisValue)
              : NaN;
        const bucket = Number.isFinite(startMs)
          ? bucketByStartMs.get(startMs)
          : undefined;

        if (!bucket) {
          return "";
        }

        const lines = [formatWindow(bucket.startMs, bucket.endMs)];

        for (const series of params) {
          const label =
            typeof series.seriesName === "string" ? series.seriesName : "Series";
          const data = Array.isArray(series.data) ? series.data : [];
          const value = data[1];
          lines.push(`${label}: ${formatTooltipValue(value)}`);
        }

        return lines.join("<br/>");
      },
    },
    xAxis: {
      type: "time",
      min: firstBucket?.startMs,
      max: lastBucket?.endMs,
      axisLabel: {
        formatter: (value: number) =>
          new Intl.DateTimeFormat(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          }).format(value),
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: {
        formatter: "{value}%",
      },
    },
    series: SERIES_META.map(({ key, name, color }) => ({
      name,
      type: "bar" as const,
      stack: "sentiment",
      itemStyle: { color },
      emphasis: { focus: "series" as const },
      data: buckets.map((bucket) => [bucket.startMs, bucket.runningPct[key]]),
    })),
  };
}
