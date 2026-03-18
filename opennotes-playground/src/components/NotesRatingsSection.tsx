import { For, Show, createMemo } from "solid-js";
import type { EChartsOption } from "echarts";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import { EChart } from "~/components/ui/echart";

type NoteQualityData = components["schemas"]["NoteQualityData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];
type TimelineBucketData = components["schemas"]["TimelineBucketData"];

function formatAxisDate(v: string): string {
  const d = new Date(v);
  const month = d.toLocaleString("en-US", { month: "short" });
  const day = d.getDate();
  const hour = d.getHours();
  const ampm = hour >= 12 ? "pm" : "am";
  const h = hour % 12 || 12;
  return `${month} ${day} ${h}${ampm}`;
}

function buildOverallBarOption(overall: Record<string, number>): EChartsOption {
  const keys = Object.keys(overall);
  return {
    grid: { left: 10, right: 10, top: 10, bottom: 30 },
    xAxis: { type: "value", show: false },
    yAxis: { type: "category", data: [""], show: false },
    series: keys.map((key) => ({
      name: humanizeLabel(key),
      type: "bar" as const,
      stack: "total",
      data: [overall[key]],
      label: { show: true, formatter: "{c}" },
    })),
    legend: { bottom: 0 },
    tooltip: { trigger: "axis" },
  };
}

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
      axisLabel: { formatter: formatAxisDate },
    },
    yAxis: { type: "value" },
    series,
  };
}

export default function NotesRatingsSection(props: {
  noteQuality: NoteQualityData;
  ratingDistribution: RatingDistributionData;
  buckets?: TimelineBucketData[];
  totalNotes?: number;
  totalRatings?: number;
}) {
  const notesByStatus = createMemo(() => Object.entries(props.noteQuality.notes_by_status));
  const notesByClassification = createMemo(() => Object.entries(props.noteQuality.notes_by_classification));
  const overallBarOption = createMemo(() => buildOverallBarOption(props.ratingDistribution.overall));

  const notesOption = createMemo(() =>
    props.buckets ? buildCumulativeOption(props.buckets, "notes_by_status", "Cumulative Notes") : null,
  );
  const ratingsOption = createMemo(() =>
    props.buckets ? buildCumulativeOption(props.buckets, "ratings_by_level", "Cumulative Ratings") : null,
  );

  return (
    <section id="notes-ratings">
      <h2 class="mb-4 text-xl font-semibold">Notes & Ratings</h2>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Overview</h3>
      <div class="mt-2 grid gap-4 sm:grid-cols-3">
        <div class="rounded-lg border border-border bg-card p-4">
          <h4 class="text-sm font-semibold">Avg Helpfulness Score</h4>
          <div class="mt-2 text-3xl font-bold">
            {props.noteQuality.avg_helpfulness_score?.toFixed(2) ?? "N/A"}
          </div>
        </div>
        <div class="col-span-2 rounded-lg border border-border bg-card p-4">
          <h4 class="mb-2 text-sm font-semibold">Overall Rating Distribution</h4>
          <p class="mb-2 text-xs text-muted-foreground">
            Total ratings: {props.ratingDistribution.total_ratings}
          </p>
          <EChart option={overallBarOption()} height="80px" />
        </div>
      </div>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Breakdown</h3>
      <div class="mt-2 grid gap-4 sm:grid-cols-2">
        <div class="rounded-lg border border-border bg-card p-4">
          <h4 class="mb-2 text-sm font-semibold">Notes by Status</h4>
          <table class="w-full text-sm" aria-label="Notes by status">
            <tbody>
              <For each={notesByStatus()}>
                {([status, count]) => (
                  <tr class="border-b border-border last:border-0">
                    <td class="py-1 text-muted-foreground">{humanizeLabel(status)}</td>
                    <td class="py-1 text-right font-medium">{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <div class="rounded-lg border border-border bg-card p-4">
          <h4 class="mb-2 text-sm font-semibold">Notes by Classification</h4>
          <table class="w-full text-sm" aria-label="Notes by classification">
            <tbody>
              <For each={notesByClassification()}>
                {([classification, count]) => (
                  <tr class="border-b border-border last:border-0">
                    <td class="py-1 text-muted-foreground">{humanizeLabel(classification)}</td>
                    <td class="py-1 text-right font-medium">{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
      </div>

      <Show when={props.buckets && props.buckets.length > 0}>
        <h3 class="mt-6 text-sm font-medium text-muted-foreground">Timelines</h3>
        <div class="mt-2 space-y-4">
          <Show when={notesOption()}>
            {(option) => (
              <div class="rounded-lg border border-border bg-card p-4">
                <h4 class="mb-2 text-sm font-medium text-muted-foreground">Cumulative Notes</h4>
                <EChart option={option()} height="350px" />
              </div>
            )}
          </Show>
          <Show when={ratingsOption()}>
            {(option) => (
              <div class="rounded-lg border border-border bg-card p-4">
                <h4 class="mb-2 text-sm font-medium text-muted-foreground">Cumulative Ratings</h4>
                <EChart option={option()} height="350px" />
              </div>
            )}
          </Show>
        </div>
      </Show>
    </section>
  );
}
