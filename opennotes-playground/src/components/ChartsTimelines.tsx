import { createMemo } from "solid-js";
import type { EChartsOption } from "echarts";
import type { components } from "~/lib/generated-types";
import { EChart } from "~/components/ui/echart";
import { humanizeLabel } from "~/lib/format";

type TimelineBucketData = components["schemas"]["TimelineBucketData"];

function buildCumulativeOption(
  buckets: TimelineBucketData[],
  field: "notes_by_status" | "ratings_by_level",
  title: string,
): EChartsOption {
  const timestamps = buckets.map((b) => b.timestamp);
  const allKeys = new Set<string>();
  for (const b of buckets) {
    const map = b[field] ?? {};
    for (const k of Object.keys(map)) allKeys.add(k);
  }

  const series = [...allKeys].map((key) => {
    let cumulative = 0;
    return {
      name: humanizeLabel(key),
      type: "line" as const,
      stack: "total",
      areaStyle: {},
      emphasis: { focus: "series" as const },
      data: buckets.map((b) => {
        cumulative += (b[field] ?? {})[key] ?? 0;
        return cumulative;
      }),
    };
  });

  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0, type: "scroll" },
    grid: { left: 50, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: "category",
      data: timestamps,
      axisLabel: {
        formatter: (v: string) =>
          new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    },
    yAxis: { type: "value" },
    series,
  };
}

export default function ChartsTimelines(props: {
  buckets: TimelineBucketData[];
  totalNotes: number;
  totalRatings: number;
}) {
  const notesOption = createMemo(() =>
    buildCumulativeOption(props.buckets, "notes_by_status", "Cumulative Notes"),
  );
  const ratingsOption = createMemo(() =>
    buildCumulativeOption(props.buckets, "ratings_by_level", "Cumulative Ratings"),
  );

  return (
    <section id="charts-timelines">
      <h2 class="mb-4 text-lg font-semibold">Charts & Timelines</h2>
      <div class="grid gap-6 lg:grid-cols-2">
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-medium text-muted-foreground">Cumulative Notes</h3>
          <EChart option={notesOption()} height="350px" />
        </div>
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-medium text-muted-foreground">Cumulative Ratings</h3>
          <EChart option={ratingsOption()} height="350px" />
        </div>
      </div>
    </section>
  );
}
