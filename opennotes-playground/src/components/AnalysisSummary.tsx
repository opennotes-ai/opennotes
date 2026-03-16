import { For, Show, createSignal, createMemo, createEffect } from "solid-js";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import InlineHistogram from "~/components/ui/inline-histogram";
import PaginationControls from "~/components/ui/pagination-controls";
import SortableHeader, { type SortDirection } from "~/components/ui/sortable-header";

type NoteQualityData = components["schemas"]["NoteQualityData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];

export default function AnalysisSummary(props: {
  noteQuality: NoteQualityData;
  ratingDistribution: RatingDistributionData;
  pageSize: number;
}) {
  const notesByStatus = createMemo(() => Object.entries(props.noteQuality.notes_by_status));
  const notesByClassification = createMemo(() => Object.entries(props.noteQuality.notes_by_classification));
  const overallRatings = createMemo(() => Object.entries(props.ratingDistribution.overall));

  const [agentPage, setAgentPage] = createSignal(1);
  const [agentSort, setAgentSort] = createSignal<{ key: string; direction: SortDirection }>({ key: "", direction: null });

  const handleAgentSort = (key: string, direction: SortDirection) => {
    setAgentSort({ key, direction });
    setAgentPage(1);
  };

  const sortedAgents = createMemo(() => {
    const agents = [...(props.ratingDistribution?.per_agent ?? [])];
    const { key, direction } = agentSort();
    if (!direction) return agents;
    const mult = direction === "asc" ? 1 : -1;
    if (key === "agent") {
      agents.sort((a, b) => mult * a.agent_name.localeCompare(b.agent_name));
    } else if (key === "total") {
      agents.sort((a, b) => mult * (a.total - b.total));
    }
    return agents;
  });

  const totalAgentPages = createMemo(() =>
    Math.ceil((sortedAgents().length) / props.pageSize)
  );
  const visibleAgents = createMemo(() => {
    const start = (agentPage() - 1) * props.pageSize;
    return sortedAgents().slice(start, start + props.pageSize);
  });

  createEffect(() => {
    props.pageSize;
    setAgentPage(1);
  });

  return (
    <section>
      <h2 id="note-quality" class="mb-4 text-xl font-semibold">Note Quality</h2>
      <div class="grid gap-4 sm:grid-cols-3">
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="text-sm font-semibold">Avg Helpfulness Score</h3>
          <div class="mt-2 text-3xl font-bold">
            {props.noteQuality.avg_helpfulness_score?.toFixed(2) ?? "N/A"}
          </div>
        </div>
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-semibold">Notes by Status</h3>
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
          <h3 class="mb-2 text-sm font-semibold">Notes by Classification</h3>
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

      <h2 id="rating-distribution" class="mb-4 mt-8 text-xl font-semibold">Rating Distribution</h2>
      <p class="mb-3 text-sm text-muted-foreground">
        Total ratings: {props.ratingDistribution.total_ratings}
      </p>
      <div class="grid items-start gap-4 sm:grid-cols-2">
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-semibold">Overall</h3>
          <table class="w-full text-sm" aria-label="Overall rating distribution">
            <tbody>
              <For each={overallRatings()}>
                {([level, count]) => (
                  <tr class="border-b border-border last:border-0">
                    <td class="py-1 text-muted-foreground">{humanizeLabel(level)}</td>
                    <td class="py-1 text-right font-medium">{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <Show when={props.ratingDistribution.per_agent.length > 0}>
          <div class="rounded-lg border border-border bg-card p-4">
            <h3 class="mb-2 text-sm font-semibold">Per Agent</h3>
            <div class="overflow-x-auto">
              <table class="w-full text-sm" aria-label="Per agent rating distribution">
                <thead>
                  <tr class="border-b-2 border-border">
                    <SortableHeader
                      label="Agent"
                      sortKey="agent"
                      activeSort={agentSort()}
                      onSort={handleAgentSort}
                      class="py-1.5 text-left font-medium text-muted-foreground"
                    />
                    <th class="py-1.5 text-left font-medium text-muted-foreground">Distribution</th>
                    <SortableHeader
                      label="Total"
                      sortKey="total"
                      activeSort={agentSort()}
                      onSort={handleAgentSort}
                      class="py-1.5 text-right font-medium text-muted-foreground"
                    />
                  </tr>
                </thead>
                <tbody>
                  <For each={visibleAgents()}>
                    {(agent) => (
                      <tr class="border-b border-border last:border-0">
                        <td class="py-1.5">{agent.agent_name}</td>
                        <td class="py-1.5">
                          <Show
                            when={Object.keys(agent.distribution).length > 0}
                            fallback={<span class="text-xs text-muted-foreground italic">No ratings</span>}
                          >
                            <InlineHistogram data={agent.distribution} />
                          </Show>
                        </td>
                        <td class="py-1.5 text-right font-medium">{agent.total}</td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
            <Show when={totalAgentPages() > 1}>
              <PaginationControls
                currentPage={agentPage()}
                totalPages={totalAgentPages()}
                onPageChange={setAgentPage}
                label="Per agent pagination"
              />
            </Show>
          </div>
        </Show>
      </div>
    </section>
  );
}
