import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import { Router, Route } from "@solidjs/router";
import type { components } from "~/lib/generated-types";
import SimulationCard from "./SimulationCard";

type SimulationResource = components["schemas"]["SimulationResource"];

function makeSimulation(overrides?: Partial<SimulationResource["attributes"]>): SimulationResource {
  return {
    type: "simulations",
    id: "sim-123",
    attributes: {
      orchestrator_id: "orch-1",
      community_server_id: "srv-1",
      status: "running",
      restart_count: 0,
      cumulative_turns: 5,
      is_public: false,
      name: "Test Simulation",
      created_at: "2026-01-01T00:00:00Z",
      metrics: { agent_count: 3, note_count: 2 },
      ...overrides,
    },
  };
}

function renderWithRouter(sim: SimulationResource) {
  return render(() => (
    <Router>
      <Route path="/" component={() => <SimulationCard simulation={sim} />} />
    </Router>
  ));
}

describe("SimulationCard", () => {
  it("renders the outer anchor with the correct simulation href", () => {
    const sim = makeSimulation();
    const { container } = renderWithRouter(sim);

    const anchor = container.querySelector("a");
    expect(anchor).not.toBeNull();
    expect(anchor?.getAttribute("href")).toBe("/simulations/sim-123");
  });

  it("renders Card from @opennotes/ui inside the anchor", () => {
    const sim = makeSimulation();
    const { container } = renderWithRouter(sim);

    const anchor = container.querySelector("a");
    const card = anchor?.querySelector("div");
    expect(card).not.toBeNull();
    expect(card?.className).toContain("rounded-lg");
    expect(card?.className).toContain("border");
    expect(card?.className).toContain("bg-card");
    expect(card?.className).toContain("p-4");
  });

  it("displays simulation status and turns", () => {
    const sim = makeSimulation({ status: "completed", cumulative_turns: 12 });
    const { getByText } = renderWithRouter(sim);

    expect(getByText("Completed")).toBeDefined();
    expect(getByText("Turns: 12")).toBeDefined();
  });
});
