import { createSignal, createMemo, createEffect, on, For, Show } from "solid-js";
import { Popover } from "@kobalte/core/popover";
import type { EChartsOption } from "echarts";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";
import InlineHistogram from "~/components/ui/inline-histogram";
import IdBadge from "~/components/ui/id-badge";
import PaginationControls from "~/components/ui/pagination-controls";
import SortableHeader, { type SortDirection } from "~/components/ui/sortable-header";
import { EChart } from "~/components/ui/echart";

type AgentBehaviorData = components["schemas"]["AgentBehaviorData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];

const STATE_VARIANT: Record<string, BadgeVariant> = {
  active: "success",
  idle: "muted",
  completed: "info",
  error: "danger",
};

function PersonalityCell(props: { text: string }) {
  const shouldTruncate = () => props.text.length > 200;

  return (
    <div class="max-w-sm text-sm text-muted-foreground">
      <Show when={props.text} fallback={<span class="italic text-xs">No persona</span>}>
        <p class="line-clamp-3 whitespace-pre-line">
          {props.text}
        </p>
        <Show when={shouldTruncate()}>
          <Popover>
            <Popover.Trigger class="text-xs text-primary hover:underline mt-1 cursor-pointer">
              Show more
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content class="z-50 max-w-md max-h-72 overflow-y-auto rounded-lg border border-border bg-popover p-4 text-sm text-popover-foreground shadow-lg">
                <Popover.Arrow class="fill-popover" />
                <p class="whitespace-pre-line leading-relaxed">{props.text}</p>
              </Popover.Content>
            </Popover.Portal>
          </Popover>
        </Show>
      </Show>
    </div>
  );
}

function buildHistogramOption(perAgent: RatingDistributionData["per_agent"]): EChartsOption {
  const agents = perAgent.map((a) => a.agent_name);
  const keys = ["HELPFUL", "SOMEWHAT_HELPFUL", "NOT_HELPFUL"];
  const maxTotal = Math.max(...perAgent.map((a) =>
    Object.values(a.distribution).reduce((s, v) => s + v, 0),
  ));

  return {
    grid: { left: 120, right: 20, top: 10, bottom: 50 },
    xAxis: { type: "value", max: maxTotal > 0 ? maxTotal : undefined },
    yAxis: { type: "category", data: [...agents].reverse() },
    series: keys.map((key) => ({
      name: humanizeLabel(key),
      type: "bar" as const,
      stack: "total",
      data: [...perAgent].reverse().map((a) => a.distribution[key] ?? 0),
    })),
    legend: { bottom: 0, type: "scroll" },
    tooltip: { trigger: "axis" },
  };
}

export default function AgentsSection(props: {
  agents: AgentBehaviorData[];
  ratingDistribution: RatingDistributionData;
  pageSize: number;
  anchorPage?: number;
}) {
  const [page, setPage] = createSignal(1);
  createEffect(() => {
    if (props.anchorPage && props.anchorPage > 0) setPage(props.anchorPage);
  });
  const [agentSort, setAgentSort] = createSignal<{ key: string; direction: SortDirection }>({ key: "", direction: null });

  const handleSort = (key: string, direction: SortDirection) => {
    setAgentSort({ key, direction });
    setPage(1);
  };

  const sortedAgents = createMemo(() => {
    const agents = [...props.agents];
    const { key, direction } = agentSort();
    if (!direction) return agents;
    const mult = direction === "asc" ? 1 : -1;
    switch (key) {
      case "agent":
        agents.sort((a, b) => mult * a.agent_name.localeCompare(b.agent_name));
        break;
      case "notes":
        agents.sort((a, b) => mult * (a.notes_written - b.notes_written));
        break;
      case "ratings":
        agents.sort((a, b) => mult * (a.ratings_given - b.ratings_given));
        break;
      case "turns":
        agents.sort((a, b) => mult * (a.turn_count - b.turn_count));
        break;
      case "model":
        agents.sort((a, b) => mult * a.display_model.localeCompare(b.display_model));
        break;
      case "state":
        agents.sort((a, b) => mult * a.state.localeCompare(b.state));
        break;
    }
    return agents;
  });

  const totalPages = createMemo(() => Math.max(1, Math.ceil(sortedAgents().length / props.pageSize)));
  createEffect(on(() => props.pageSize, () => setPage(1), { defer: true }));
  createEffect(() => {
    if (page() > totalPages()) setPage(totalPages());
  });
  const visibleAgents = createMemo(() => {
    const start = (page() - 1) * props.pageSize;
    return sortedAgents().slice(start, start + props.pageSize);
  });

  const histogramOption = createMemo(() =>
    props.ratingDistribution.per_agent.length > 0
      ? buildHistogramOption(props.ratingDistribution.per_agent)
      : null,
  );

  const histogramHeight = createMemo(() =>
    `${Math.max(300, props.ratingDistribution.per_agent.length * 28)}px`,
  );

  return (
    <section id="agents">
      <h2 class="mb-4 text-xl font-semibold">Agents</h2>
      <div class="overflow-x-auto rounded-lg border border-border">
        <table class="w-full text-sm" aria-label="Agent profiles">
          <thead>
            <tr class="border-b-2 border-border bg-muted/50">
              <SortableHeader label="Agent" sortKey="agent" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-left font-medium" />
              <SortableHeader label="Model" sortKey="model" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-left font-medium" />
              <th class="px-4 py-2.5 text-left font-medium">Persona</th>
              <SortableHeader label="Notes" sortKey="notes" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-right font-medium" />
              <SortableHeader label="Ratings" sortKey="ratings" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-right font-medium" />
              <SortableHeader label="Turns" sortKey="turns" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-right font-medium" />
              <SortableHeader label="State" sortKey="state" activeSort={agentSort()} onSort={handleSort} class="px-4 py-2.5 text-left font-medium" />
              <th class="px-4 py-2.5 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            <For each={visibleAgents()}>
              {(agent) => (
                <tr id={`agent-${agent.agent_profile_id}`} class="border-b border-border last:border-0 hover:bg-muted/30">
                  <td class="px-4 py-2.5 min-w-48">
                    <div class="font-medium">{agent.agent_name}</div>
                    <Show when={agent.short_description}>
                      <div class="text-xs text-muted-foreground">{agent.short_description}</div>
                    </Show>
                    <div class="text-xs text-muted-foreground">
                      <IdBadge idValue={agent.agent_profile_id} variant="muted" />
                    </div>
                  </td>
                  <td class="px-4 py-2.5 text-sm text-muted-foreground max-w-32 break-words">{agent.display_model}</td>
                  <td class="px-4 py-2.5">
                    <PersonalityCell text={agent.personality} />
                  </td>
                  <td class="px-4 py-2.5 text-right tabular-nums">{agent.notes_written}</td>
                  <td class="px-4 py-2.5 text-right tabular-nums">{agent.ratings_given}</td>
                  <td class="px-4 py-2.5 text-right tabular-nums">{agent.turn_count}</td>
                  <td class="px-4 py-2.5">
                    <Badge variant={STATE_VARIANT[agent.state] ?? "muted"}>
                      {humanizeLabel(agent.state)}
                    </Badge>
                  </td>
                  <td class="px-4 py-2.5">
                    <Show
                      when={Object.keys(agent.action_distribution).length > 0}
                      fallback={
                        <span class="text-xs text-muted-foreground italic">
                          No actions
                        </span>
                      }
                    >
                      <InlineHistogram data={agent.action_distribution} />
                    </Show>
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
      </div>
      <Show when={totalPages() > 1}>
        <PaginationControls
          currentPage={page()}
          totalPages={totalPages()}
          onPageChange={setPage}
          label="Agent table pagination"
        />
      </Show>

      <Show when={histogramOption()}>
        {(option) => (
          <div class="mt-6 rounded-lg border border-border bg-card p-4">
            <h3 class="mb-2 text-sm font-medium text-muted-foreground">Per-Agent Rating Distribution</h3>
            <EChart option={option()} height={histogramHeight()} />
          </div>
        )}
      </Show>
    </section>
  );
}
