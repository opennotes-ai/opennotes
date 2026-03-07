import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type NoteQualityData = components["schemas"]["NoteQualityData"];
type RatingDistributionData = components["schemas"]["RatingDistributionData"];

export default function AnalysisSummary(props: {
  noteQuality: NoteQualityData;
  ratingDistribution: RatingDistributionData;
}) {
  return (
    <section>
      <h2>Note Quality</h2>
      <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap" }}>
        <div>
          <strong>Avg Helpfulness Score</strong>
          <div style={{ "font-size": "1.5rem", "margin-top": "0.25rem" }}>
            {props.noteQuality.avg_helpfulness_score?.toFixed(2) ?? "N/A"}
          </div>
        </div>
        <div>
          <strong>Notes by Status</strong>
          <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
            <tbody>
              <For each={Object.entries(props.noteQuality.notes_by_status)}>
                {([status, count]) => (
                  <tr>
                    <td style={{ padding: "0.15rem 0.75rem 0.15rem 0", color: "#555" }}>{status}</td>
                    <td style={{ padding: "0.15rem 0", "font-weight": "600" }}>{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <div>
          <strong>Notes by Classification</strong>
          <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
            <tbody>
              <For each={Object.entries(props.noteQuality.notes_by_classification)}>
                {([classification, count]) => (
                  <tr>
                    <td style={{ padding: "0.15rem 0.75rem 0.15rem 0", color: "#555" }}>{classification}</td>
                    <td style={{ padding: "0.15rem 0", "font-weight": "600" }}>{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
      </div>

      <h2 style={{ "margin-top": "1.5rem" }}>Rating Distribution</h2>
      <p style={{ color: "#666" }}>Total ratings: {props.ratingDistribution.total_ratings}</p>
      <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap" }}>
        <div>
          <strong>Overall</strong>
          <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
            <tbody>
              <For each={Object.entries(props.ratingDistribution.overall)}>
                {([level, count]) => (
                  <tr>
                    <td style={{ padding: "0.15rem 0.75rem 0.15rem 0", color: "#555" }}>{level}</td>
                    <td style={{ padding: "0.15rem 0", "font-weight": "600" }}>{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <Show when={props.ratingDistribution.per_agent.length > 0}>
          <div>
            <strong>Per Agent</strong>
            <table style={{ "margin-top": "0.25rem", "border-collapse": "collapse" }}>
              <thead>
                <tr>
                  <th style={{ padding: "0.25rem 0.75rem 0.25rem 0", "text-align": "left" }}>Agent</th>
                  <th style={{ padding: "0.25rem 0.75rem", "text-align": "left" }}>Distribution</th>
                  <th style={{ padding: "0.25rem 0", "text-align": "right" }}>Total</th>
                </tr>
              </thead>
              <tbody>
                <For each={props.ratingDistribution.per_agent}>
                  {(agent) => (
                    <tr>
                      <td style={{ padding: "0.25rem 0.75rem 0.25rem 0" }}>{agent.agent_name}</td>
                      <td style={{ padding: "0.25rem 0.75rem", color: "#555", "font-size": "0.85rem" }}>
                        {Object.entries(agent.distribution)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(", ")}
                      </td>
                      <td style={{ padding: "0.25rem 0", "text-align": "right", "font-weight": "600" }}>
                        {agent.total}
                      </td>
                    </tr>
                  )}
                </For>
              </tbody>
            </table>
          </div>
        </Show>
      </div>
    </section>
  );
}
