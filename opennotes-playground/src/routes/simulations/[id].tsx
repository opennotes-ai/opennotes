import { query, createAsync, useParams } from "@solidjs/router";
import { Show, Suspense } from "solid-js";
import {
  getSimulation,
  getSimulationAnalysis,
  getSimulationDetailedAnalysis,
} from "~/lib/api-client.server";
import AnalysisSummary from "~/components/AnalysisSummary";
import AgentProfiles from "~/components/AgentProfiles";
import MetricsDisplay from "~/components/MetricsDisplay";
import NoteDetails from "~/components/NoteDetails";

const fetchSimulation = query(async (id: string) => {
  "use server";
  try {
    return await getSimulation(id);
  } catch {
    return null;
  }
}, "simulation");

const fetchAnalysis = query(async (id: string) => {
  "use server";
  try {
    return await getSimulationAnalysis(id);
  } catch {
    return null;
  }
}, "analysis");

const fetchDetailedAnalysis = query(async (id: string) => {
  "use server";
  try {
    return await getSimulationDetailedAnalysis(id, 1, 50);
  } catch {
    return null;
  }
}, "detailed-analysis");

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  return new Date(dateStr).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getMetric(
  metrics: Record<string, unknown> | null | undefined,
  key: string,
): string {
  if (!metrics || !(key in metrics)) return "N/A";
  return String(metrics[key]);
}

export default function SimulationDetailPage() {
  const params = useParams();
  const simulation = createAsync(() => fetchSimulation(params.id));
  const analysis = createAsync(() => fetchAnalysis(params.id));
  const detailed = createAsync(() => fetchDetailedAnalysis(params.id));

  return (
    <main style={{ "max-width": "960px", margin: "0 auto", padding: "2rem 1rem" }}>
      <Suspense fallback={<p>Loading simulation...</p>}>
        <Show when={simulation()} fallback={<NotFound />} keyed>
          {(simResponse) => {
            const attrs = simResponse.data.attributes;
            return (
              <>
                <div style={{ display: "flex", "justify-content": "space-between", "align-items": "center", "flex-wrap": "wrap", gap: "0.5rem" }}>
                  <h1 style={{ margin: "0" }}>Simulation {simResponse.data.id.slice(0, 8)}</h1>
                  <StatusBadge status={attrs.status} />
                </div>

                <section style={{ "margin-top": "1rem" }}>
                  <h2>Metadata</h2>
                  <div style={{ display: "flex", gap: "2rem", "flex-wrap": "wrap", "font-size": "0.9rem" }}>
                    <div>
                      <span style={{ color: "#666" }}>Status: </span>
                      <strong>{attrs.status}</strong>
                    </div>
                    <div>
                      <span style={{ color: "#666" }}>Created: </span>
                      {formatDate(attrs.created_at)}
                    </div>
                    <Show when={attrs.started_at}>
                      <div>
                        <span style={{ color: "#666" }}>Started: </span>
                        {formatDate(attrs.started_at)}
                      </div>
                    </Show>
                    <Show when={attrs.completed_at}>
                      <div>
                        <span style={{ color: "#666" }}>Completed: </span>
                        {formatDate(attrs.completed_at)}
                      </div>
                    </Show>
                    <div>
                      <span style={{ color: "#666" }}>Agents: </span>
                      <strong>{getMetric(attrs.metrics, "agent_count")}</strong>
                    </div>
                    <div>
                      <span style={{ color: "#666" }}>Notes: </span>
                      <strong>{getMetric(attrs.metrics, "note_count")}</strong>
                    </div>
                    <div>
                      <span style={{ color: "#666" }}>Turns: </span>
                      <strong>{attrs.cumulative_turns}</strong>
                    </div>
                    <div>
                      <span style={{ color: "#666" }}>Restarts: </span>
                      {attrs.restart_count}
                    </div>
                  </div>
                  <Show when={attrs.error_message}>
                    <div
                      style={{
                        "margin-top": "0.75rem",
                        padding: "0.5rem 0.75rem",
                        "background-color": "#f8d7da",
                        color: "#721c24",
                        "border-radius": "4px",
                        "font-size": "0.85rem",
                      }}
                    >
                      Error: {attrs.error_message}
                    </div>
                  </Show>
                  <div style={{ "margin-top": "0.5rem", "font-size": "0.8rem", color: "#999" }}>
                    Orchestrator: {attrs.orchestrator_id?.slice(0, 8) ?? "N/A"} | Community Server: {attrs.community_server_id?.slice(0, 8) ?? "N/A"}
                  </div>
                </section>

                <hr style={{ margin: "1.5rem 0", border: "none", "border-top": "1px solid #eee" }} />

                <Suspense fallback={<p>Loading analysis...</p>}>
                  <Show when={analysis()} keyed>
                    {(analysisResponse) => {
                      const a = analysisResponse.data.attributes;
                      return (
                        <>
                          <AnalysisSummary
                            noteQuality={a.note_quality}
                            ratingDistribution={a.rating_distribution}
                          />

                          <hr style={{ margin: "1.5rem 0", border: "none", "border-top": "1px solid #eee" }} />

                          <MetricsDisplay
                            consensus={a.consensus_metrics}
                            scoring={a.scoring_coverage}
                          />

                          <hr style={{ margin: "1.5rem 0", border: "none", "border-top": "1px solid #eee" }} />

                          <AgentProfiles agents={a.agent_behaviors} />
                        </>
                      );
                    }}
                  </Show>
                </Suspense>

                <hr style={{ margin: "1.5rem 0", border: "none", "border-top": "1px solid #eee" }} />

                <Suspense fallback={<p>Loading detailed analysis...</p>}>
                  <Show when={detailed()} keyed>
                    {(detailedResponse) => (
                      <>
                        <Show when={detailedResponse.meta}>
                          {(meta) => (
                            <p style={{ color: "#666", "font-size": "0.9rem" }}>
                              {meta().count} note{meta().count !== 1 ? "s" : ""} in detailed analysis
                            </p>
                          )}
                        </Show>
                        <NoteDetails notes={detailedResponse.data} />
                      </>
                    )}
                  </Show>
                </Suspense>
              </>
            );
          }}
        </Show>
      </Suspense>
    </main>
  );
}

function NotFound() {
  return (
    <div style={{ "text-align": "center", "margin-top": "4rem" }}>
      <h1>404</h1>
      <p style={{ color: "#666" }}>Simulation not found.</p>
      <a href="/simulations" style={{ color: "#1976d2" }}>Back to simulations</a>
    </div>
  );
}

function StatusBadge(props: { status: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    completed: { bg: "#d4edda", fg: "#155724" },
    running: { bg: "#fff3cd", fg: "#856404" },
    pending: { bg: "#e2e3e5", fg: "#383d41" },
    failed: { bg: "#f8d7da", fg: "#721c24" },
    paused: { bg: "#cce5ff", fg: "#004085" },
  };
  const style = () => colors[props.status] ?? { bg: "#e2e3e5", fg: "#383d41" };

  return (
    <span
      style={{
        "background-color": style().bg,
        color: style().fg,
        padding: "0.25rem 0.75rem",
        "border-radius": "4px",
        "font-size": "0.85rem",
        "font-weight": "600",
        "text-transform": "uppercase",
      }}
    >
      {props.status}
    </span>
  );
}
