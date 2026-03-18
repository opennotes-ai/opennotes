import type { components } from "~/lib/generated-types";

type ConsensusMetricsData = components["schemas"]["ConsensusMetricsData"];
type ScoringCoverageData = components["schemas"]["ScoringCoverageData"];

export default function ScoringAnalysisSection(props: {
  consensus: ConsensusMetricsData;
  scoring: ScoringCoverageData;
}) {
  return (
    <section id="scoring-analysis">
      <h2 class="mb-4 text-xl font-semibold">Scoring & Analysis</h2>
      <p class="text-sm text-muted-foreground">
        Consensus metrics and scoring coverage
      </p>
    </section>
  );
}
