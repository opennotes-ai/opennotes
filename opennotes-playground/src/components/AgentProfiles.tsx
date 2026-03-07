import { For } from "solid-js";
import type { components } from "~/lib/generated-types";

type AgentBehaviorData = components["schemas"]["AgentBehaviorData"];

export default function AgentProfiles(props: { agents: AgentBehaviorData[] }) {
  return (
    <section>
      <h2>Agent Behaviors</h2>
      <div style={{ "overflow-x": "auto" }}>
        <table style={{ width: "100%", "border-collapse": "collapse" }}>
          <thead>
            <tr style={{ "border-bottom": "2px solid #ddd" }}>
              <th style={{ padding: "0.5rem", "text-align": "left" }}>Agent</th>
              <th style={{ padding: "0.5rem", "text-align": "right" }}>Notes Written</th>
              <th style={{ padding: "0.5rem", "text-align": "right" }}>Ratings Given</th>
              <th style={{ padding: "0.5rem", "text-align": "right" }}>Turns</th>
              <th style={{ padding: "0.5rem", "text-align": "left" }}>State</th>
              <th style={{ padding: "0.5rem", "text-align": "left" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            <For each={props.agents}>
              {(agent) => (
                <tr style={{ "border-bottom": "1px solid #eee" }}>
                  <td style={{ padding: "0.5rem" }}>
                    <strong>{agent.agent_name}</strong>
                    <div style={{ "font-size": "0.75rem", color: "#999" }}>
                      {agent.agent_instance_id.slice(0, 8)}
                    </div>
                  </td>
                  <td style={{ padding: "0.5rem", "text-align": "right" }}>{agent.notes_written}</td>
                  <td style={{ padding: "0.5rem", "text-align": "right" }}>{agent.ratings_given}</td>
                  <td style={{ padding: "0.5rem", "text-align": "right" }}>{agent.turn_count}</td>
                  <td style={{ padding: "0.5rem" }}>
                    <StateBadge state={agent.state} />
                  </td>
                  <td style={{ padding: "0.5rem", "font-size": "0.85rem", color: "#555" }}>
                    {Object.entries(agent.action_distribution)
                      .map(([action, count]) => `${action}: ${count}`)
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

function StateBadge(props: { state: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    active: { bg: "#d4edda", fg: "#155724" },
    idle: { bg: "#e2e3e5", fg: "#383d41" },
    completed: { bg: "#cce5ff", fg: "#004085" },
    error: { bg: "#f8d7da", fg: "#721c24" },
  };
  const style = () => colors[props.state] ?? { bg: "#e2e3e5", fg: "#383d41" };

  return (
    <span
      style={{
        "background-color": style().bg,
        color: style().fg,
        padding: "0.15rem 0.4rem",
        "border-radius": "3px",
        "font-size": "0.75rem",
        "font-weight": "600",
        "text-transform": "uppercase",
      }}
    >
      {props.state}
    </span>
  );
}
