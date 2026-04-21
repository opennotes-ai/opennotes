import { A } from "@solidjs/router";
import type { components } from "~/lib/generated-types";
import { formatDate, getMetric, humanizeLabel } from "@opennotes/ui/utils";
import { Badge, type BadgeVariant } from "@opennotes/ui/components/ui/badge";
import IdBadge from "@opennotes/ui/components/ui/id-badge";

type SimulationResource = components["schemas"]["SimulationResource"];

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  completed: "success",
  running: "warning",
  pending: "muted",
  failed: "danger",
  paused: "info",
};

export default function SimulationCard(props: { simulation: SimulationResource }) {
  const sim = () => props.simulation;
  const attrs = () => sim().attributes;

  return (
    <A
      href={`/simulations/${sim().id}`}
      class="block rounded-lg border border-border bg-card p-4 no-underline transition-colors hover:border-primary/40 hover:bg-muted/50"
    >
      <div class="flex items-center justify-between">
        <span class="text-base font-semibold">
          Simulation <IdBadge idValue={sim().id} name={attrs().name} variant="muted" />
        </span>
        <Badge variant={STATUS_VARIANT[attrs().status] ?? "muted"}>
          {humanizeLabel(attrs().status)}
        </Badge>
      </div>
      <div class="mt-2 text-sm text-muted-foreground">
        <div>Created: {formatDate(attrs().created_at)}</div>
        <div class="mt-1 flex gap-4">
          <span>Agents: {getMetric(attrs().metrics, "agent_count")}</span>
          <span>Notes: {getMetric(attrs().metrics, "note_count")}</span>
          <span>Turns: {attrs().cumulative_turns}</span>
        </div>
      </div>
    </A>
  );
}
