import type { components } from "~/lib/generated-types";

type AgentBehaviorData = components["schemas"]["AgentBehaviorData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];

export default function AgentsSection(props: {
  agents: AgentBehaviorData[];
  ratingDistribution: RatingDistributionData;
  pageSize: number;
}) {
  return (
    <section id="agents">
      <h2 class="mb-4 text-xl font-semibold">Agents</h2>
      <p class="text-sm text-muted-foreground">
        {props.agents.length} agent profiles
      </p>
    </section>
  );
}
