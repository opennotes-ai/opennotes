import { createSignal, For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import { humanizeLabel, truncateId } from "~/lib/format";
import { Badge, type BadgeVariant } from "~/components/ui/badge";

type AgentBehaviorData = components["schemas"]["AgentBehaviorData"];

const STATE_VARIANT: Record<string, BadgeVariant> = {
  active: "success",
  idle: "muted",
  completed: "info",
  error: "danger",
};

function PersonalityCell(props: { text: string }) {
  const [expanded, setExpanded] = createSignal(false);
  const shouldTruncate = () => props.text.length > 120;

  return (
    <div class="max-w-xs text-sm text-muted-foreground">
      <Show when={props.text} fallback={<span class="italic text-xs">No persona</span>}>
        <p class={expanded() ? "whitespace-pre-line" : "line-clamp-2 whitespace-pre-line"}>
          {props.text}
        </p>
        <Show when={shouldTruncate()}>
          <button
            class="text-xs text-primary hover:underline mt-1"
            onClick={() => setExpanded(!expanded())}
          >
            {expanded() ? "Show less" : "Show more"}
          </button>
        </Show>
      </Show>
    </div>
  );
}

export default function AgentProfiles(props: { agents: AgentBehaviorData[] }) {
  return (
    <section>
      <h2 class="mb-4 text-xl font-semibold">Agent Behaviors</h2>
      <div class="overflow-x-auto rounded-lg border border-border">
        <table class="w-full text-sm" aria-label="Agent behaviors">
          <thead>
            <tr class="border-b-2 border-border bg-muted/50">
              <th class="px-4 py-2.5 text-left font-medium">Agent</th>
              <th class="px-4 py-2.5 text-left font-medium">Persona</th>
              <th class="px-4 py-2.5 text-right font-medium">Notes</th>
              <th class="px-4 py-2.5 text-right font-medium">Ratings</th>
              <th class="px-4 py-2.5 text-right font-medium">Turns</th>
              <th class="px-4 py-2.5 text-left font-medium">State</th>
              <th class="px-4 py-2.5 text-left font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            <For each={props.agents}>
              {(agent) => (
                <tr class="border-b border-border last:border-0 hover:bg-muted/30">
                  <td class="px-4 py-2.5">
                    <div class="font-medium">{agent.agent_name}</div>
                    <div class="text-xs text-muted-foreground">
                      {truncateId(agent.agent_instance_id)}
                    </div>
                  </td>
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
                  <td class="px-4 py-2.5 text-muted-foreground">
                    {Object.entries(agent.action_distribution)
                      .map(([action, count]) => `${humanizeLabel(action)}: ${count}`)
                      .join(", ")}
                  </td>
                </tr>
              )}
            </For>
          </tbody>
        </table>
      </div>
    </section>
  );
}
