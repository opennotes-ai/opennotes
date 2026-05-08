import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type ClaimTrend = components["schemas"]["ClaimTrend"];
type ClaimOpposition = components["schemas"]["ClaimOpposition"];
type TrendsOppositionsReport = components["schemas"]["TrendsOppositionsReport"];

export interface TrendsOppositionsReportProps {
  report: TrendsOppositionsReport | null;
}

export const EMPTY_TRENDS_OPPOSITIONS_REPORT: TrendsOppositionsReport = {
  trends: [],
  oppositions: [],
  input_cluster_count: 0,
  skipped_for_cap: 0,
};

function hasNoContent(report: TrendsOppositionsReport | null): boolean {
  if (!report) return true;
  return (report.trends ?? []).length === 0 && (report.oppositions ?? []).length === 0;
}

function TrendListItem(props: { trend: ClaimTrend }) {
  const clusterCount = () => props.trend.cluster_texts.length;
  return (
    <li data-testid="trends-opposition-trend" class="rounded-md border border-border/50 p-2">
      <div class="mb-1 flex items-start justify-between gap-2 text-xs">
        <p class="font-semibold text-foreground">{props.trend.label}</p>
        <span
          data-testid="trends-opposition-trend-count"
          class="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium tabular-nums text-muted-foreground"
          title="Number of clusters"
        >
          {clusterCount()} cluster{clusterCount() === 1 ? "" : "s"}
        </span>
      </div>
      <p class="text-xs leading-relaxed text-muted-foreground">
        {props.trend.summary}
      </p>
    </li>
  );
}

function ClusterTextList(props: {
  texts: string[];
  testId: string;
}) {
  return (
    <ul class="space-y-1">
      <For each={props.texts}>
        {(text, idx) => (
          <li class="rounded-sm bg-muted/50 px-2 py-1">
            <ExpandableText
              text={text}
              lines={2}
              testId={`${props.testId}-${idx()}`}
              class="text-foreground break-words"
            />
          </li>
        )}
      </For>
    </ul>
  );
}

function OppositionRow(props: { opposition: ClaimOpposition }) {
  return (
    <li class="rounded-md border border-border/50 p-2">
      <div class="min-w-0">
        <ExpandableText
          text={props.opposition.topic}
          lines={2}
          testId="trends-opposition-topic"
          class="mb-2 break-words text-xs font-semibold text-foreground"
        />
      </div>
      <Show when={props.opposition.note}>
        <div class="min-w-0">
          <ExpandableText
            text={props.opposition.note ?? ""}
            lines={3}
            testId="trends-opposition-note"
            class="mb-2 break-words text-[11px] text-muted-foreground"
          />
        </div>
      </Show>
      <div class="grid grid-cols-2 gap-3 text-[11px]">
        <div class="min-w-0">
          <h4 class="mb-1 font-semibold uppercase tracking-wide text-muted-foreground">
            In favor
          </h4>
          <ClusterTextList
            texts={props.opposition.supporting_cluster_texts}
            testId="trends-opposition-supporting"
          />
        </div>
        <div class="min-w-0">
          <h4 class="mb-1 font-semibold uppercase tracking-wide text-muted-foreground">
            Against
          </h4>
          <ClusterTextList
            texts={props.opposition.opposing_cluster_texts}
            testId="trends-opposition-opposing"
          />
        </div>
      </div>
    </li>
  );
}

export default function TrendsOppositionsReport(props: TrendsOppositionsReportProps) {
  const report = () => props.report;
  const trends = () => report()?.trends ?? [];
  const oppositions = () => report()?.oppositions ?? [];

  return (
    <Show when={!hasNoContent(report())}>
      <div
        data-testid="report-opinions_sentiments__trends_oppositions"
        class="relative space-y-4"
      >
        <Show when={trends().length > 0}>
          <section>
            <h4 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground">
              Recurring patterns
            </h4>
            <ul class="space-y-2">
              <For each={trends()}>
                {(trend) => <TrendListItem trend={trend} />}
              </For>
            </ul>
          </section>
        </Show>
        <Show when={oppositions().length > 0}>
          <section>
            <h4 class="mb-2 text-xs font-semibold tracking-wide text-muted-foreground">
              Counter-positions
            </h4>
            <ul class="space-y-2">
              <For each={oppositions()}>
                {(opposition) => <OppositionRow opposition={opposition} />}
              </For>
            </ul>
          </section>
        </Show>
        <FeedbackBell bell_location="card:trends-oppositions" />
      </div>
    </Show>
  );
}
