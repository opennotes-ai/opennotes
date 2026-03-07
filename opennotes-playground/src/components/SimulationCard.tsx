import { A } from "@solidjs/router";
import type { components } from "~/lib/generated-types";

type SimulationResource = components["schemas"]["SimulationResource"];

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

function getMetric(metrics: Record<string, unknown> | null | undefined, key: string): string {
  if (!metrics || !(key in metrics)) return "N/A";
  return String(metrics[key]);
}

export default function SimulationCard(props: { simulation: SimulationResource }) {
  const sim = () => props.simulation;
  const attrs = () => sim().attributes;

  return (
    <A
      href={`/simulations/${sim().id}`}
      style={{
        display: "block",
        border: "1px solid #ddd",
        "border-radius": "8px",
        padding: "1rem",
        "margin-bottom": "1rem",
        "text-decoration": "none",
        color: "inherit",
      }}
    >
      <div style={{ display: "flex", "justify-content": "space-between", "align-items": "center" }}>
        <strong style={{ "font-size": "1.1rem" }}>Simulation {sim().id.slice(0, 8)}</strong>
        <StatusBadge status={attrs().status} />
      </div>
      <div style={{ "margin-top": "0.5rem", color: "#666", "font-size": "0.9rem" }}>
        <div>Created: {formatDate(attrs().created_at)}</div>
        <div style={{ display: "flex", gap: "1.5rem", "margin-top": "0.25rem" }}>
          <span>Agents: {getMetric(attrs().metrics, "agent_count")}</span>
          <span>Notes: {getMetric(attrs().metrics, "note_count")}</span>
          <span>Turns: {attrs().cumulative_turns}</span>
        </div>
      </div>
    </A>
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
        padding: "0.25rem 0.5rem",
        "border-radius": "4px",
        "font-size": "0.8rem",
        "font-weight": "600",
        "text-transform": "uppercase",
      }}
    >
      {props.status}
    </span>
  );
}
