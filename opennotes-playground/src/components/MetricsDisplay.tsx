import { For } from "solid-js";
import type { components } from "~/lib/generated-types";

type ConsensusMetricsData = components["schemas"]["ConsensusMetricsData"];
type ScoringCoverageData = components["schemas"]["ScoringCoverageData"];

export default function MetricsDisplay(props: {
  consensus: ConsensusMetricsData;
  scoring: ScoringCoverageData;
}) {
  return (
    <section>
      <h2>Consensus Metrics</h2>
      <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap", "margin-bottom": "1rem" }}>
        <MetricCard label="Mean Agreement" value={props.consensus.mean_agreement.toFixed(3)} />
        <MetricCard label="Polarization Index" value={props.consensus.polarization_index.toFixed(3)} />
        <MetricCard label="Notes with Consensus" value={String(props.consensus.notes_with_consensus)} />
        <MetricCard label="Notes with Disagreement" value={String(props.consensus.notes_with_disagreement)} />
        <MetricCard label="Total Notes Rated" value={String(props.consensus.total_notes_rated)} />
      </div>

      <h2>Scoring Coverage</h2>
      <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap", "margin-bottom": "1rem" }}>
        <MetricCard label="Current Tier" value={props.scoring.current_tier} />
        <MetricCard label="Total Scores Computed" value={String(props.scoring.total_scores_computed)} />
      </div>

      <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap" }}>
        <div>
          <strong>Tier Distribution</strong>
          <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
            <tbody>
              <For each={Object.entries(props.scoring.tier_distribution)}>
                {([tier, count]) => (
                  <tr>
                    <td style={{ padding: "0.15rem 0.75rem 0.15rem 0", color: "#555" }}>{tier}</td>
                    <td style={{ padding: "0.15rem 0", "font-weight": "600" }}>{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <div>
          <strong>Scorer Breakdown</strong>
          <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
            <tbody>
              <For each={Object.entries(props.scoring.scorer_breakdown)}>
                {([scorer, count]) => (
                  <tr>
                    <td style={{ padding: "0.15rem 0.75rem 0.15rem 0", color: "#555" }}>{scorer}</td>
                    <td style={{ padding: "0.15rem 0", "font-weight": "600" }}>{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <div>
          <strong>Tiers Reached</strong>
          <div style={{ "margin-top": "0.25rem", color: "#555" }}>
            {props.scoring.tiers_reached.join(", ") || "None"}
          </div>
        </div>
        <div>
          <strong>Scorers Exercised</strong>
          <div style={{ "margin-top": "0.25rem", color: "#555" }}>
            {props.scoring.scorers_exercised.join(", ") || "None"}
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <div
      style={{
        border: "1px solid #eee",
        "border-radius": "6px",
        padding: "0.75rem 1rem",
        "min-width": "120px",
      }}
    >
      <div style={{ "font-size": "0.8rem", color: "#666" }}>{props.label}</div>
      <div style={{ "font-size": "1.25rem", "font-weight": "600", "margin-top": "0.25rem" }}>
        {props.value}
      </div>
    </div>
  );
}
