import { For, Show, createMemo } from "solid-js";
import type { EChartsOption } from "echarts";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import { SEMANTIC_COLORS } from "@opennotes/ui/palettes";
import { EChart } from "@opennotes/ui/components/ui/echart";
import SectionHeader from "@opennotes/ui/components/ui/section-header";

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
      ...(SEMANTIC_COLORS[key] ? { itemStyle: { color: SEMANTIC_COLORS[key] } } : {}),
    })),
    legend: { bottom: 0 },
    tooltip: { trigger: "axis", axisPointer: { type: "none" } },
  };
}

function buildCumulativeOption(
  buckets: TimelineBucketData[],
  field: "notes_by_status" | "ratings_by_level",
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
      ...(SEMANTIC_COLORS[key] ? { itemStyle: { color: SEMANTIC_COLORS[key] }, lineStyle: { color: SEMANTIC_COLORS[key] }, areaStyle: { color: SEMANTIC_COLORS[key], opacity: 0.3 } } : {}),
      data: buckets.map((b) => {
        cumulative += (b[field] ?? {})[key] ?? 0;
        return cumulative;
      }),
    };
  });

  return {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0, type: "scroll" },
    grid: { left: 10, right: 20, top: 30, bottom: 40 },
    xAxis: {
      type: "category",
      data: timestamps,
      axisLabel: { formatter: formatAxisDate },
    },
    yAxis: {
      type: "value",
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
    },
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
    props.buckets ? buildCumulativeOption(props.buckets, "notes_by_status") : null,
  );
  const ratingsOption = createMemo(() =>
    props.buckets ? buildCumulativeOption(props.buckets, "ratings_by_level") : null,
  );

  return (
    <section id="notes-ratings">
      <SectionHeader title="Notes & Ratings" subtitle="What was written and how the community received it" />

      <div class="mt-4 flex flex-wrap gap-3">
        <div class="rounded-lg bg-muted/50 p-3">
          <div class="text-xs font-medium text-muted-foreground">Avg Helpfulness</div>
          <div class="mt-1 text-2xl font-bold">
            {props.noteQuality.avg_helpfulness_score?.toFixed(2) ?? "N/A"}
          </div>
        </div>
        <div class="rounded-lg bg-muted/50 p-3">
          <div class="text-xs font-medium text-muted-foreground">Total Ratings</div>
          <div class="mt-1 text-2xl font-bold">{props.ratingDistribution.total_ratings}</div>
        </div>
        <div class="min-w-[200px] flex-1 rounded-lg bg-muted/50 p-3">
          <div class="mb-1 text-xs font-medium text-muted-foreground">Overall Distribution</div>
          <EChart option={overallBarOption()} height="60px" />
        </div>
      </div>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Breakdown</h3>
      <div class="mt-2 grid gap-4 sm:grid-cols-2">
        <div class="rounded-lg border border-border p-4">
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
        <div class="rounded-lg border border-border p-4">
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
              <div class="rounded-lg bg-muted/20 p-6">
                <h4 class="mb-2 text-sm font-medium text-muted-foreground">Cumulative Notes</h4>
                <EChart option={option()} height="350px" />
              </div>
            )}
          </Show>
          <Show when={ratingsOption()}>
            {(option) => (
              <div class="rounded-lg bg-muted/20 p-6">
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
