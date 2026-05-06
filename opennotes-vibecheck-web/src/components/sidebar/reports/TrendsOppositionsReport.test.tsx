import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import TrendsOppositionsReport from "./TrendsOppositionsReport";

type TrendsOppositionsReport = components["schemas"]["TrendsOppositionsReport"];
type ClaimTrend = components["schemas"]["ClaimTrend"];
type ClaimOpposition = components["schemas"]["ClaimOpposition"];

const makeTrend = (overrides: Partial<ClaimTrend> = {}): ClaimTrend => ({
  label: "Recurring trend",
  cluster_ids: ["cluster-a", "cluster-b"],
  summary: "Pattern appears repeatedly when discussing policy tradeoffs.",
  ...overrides,
});

const makeOpposition = (
  overrides: Partial<ClaimOpposition> = {},
): ClaimOpposition => ({
  topic: "Policy outcomes",
  supporting_cluster_ids: ["cluster-pro"],
  opposing_cluster_ids: ["cluster-con"],
  note: "Both sides repeat the same evidence but change interpretation.",
  ...overrides,
});

function makeReport(
  overrides: Partial<TrendsOppositionsReport> = {},
): TrendsOppositionsReport {
  return {
    trends: [],
    oppositions: [],
    input_cluster_count: 2,
    skipped_for_cap: 0,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("TrendsOppositionsReport", () => {
  it("renders nothing when report is null", () => {
    render(() => <TrendsOppositionsReport report={null} />);
    expect(
      screen.queryByTestId("report-opinions_sentiments__trends_oppositions"),
    ).toBeNull();
  });

  it("renders nothing when both trend and opposition lists are empty", () => {
    render(() => (
      <TrendsOppositionsReport report={makeReport({ trends: [], oppositions: [] })} />
    ));
    expect(
      screen.queryByTestId("report-opinions_sentiments__trends_oppositions"),
    ).toBeNull();
  });

  it("renders recurring patterns section with label, summary, and cluster count", () => {
    render(() => (
      <TrendsOppositionsReport
        report={makeReport({ trends: [makeTrend()], oppositions: [] })}
      />
    ));

    expect(
      screen.getByTestId("report-opinions_sentiments__trends_oppositions"),
    ).toBeDefined();
    expect(screen.getByText("Recurring patterns")).toBeDefined();
    expect(screen.getByText("Recurring trend")).toBeDefined();
    expect(screen.getByText("Pattern appears repeatedly when discussing policy tradeoffs.")).toBeDefined();
    expect(screen.getByText("2 clusters")).toBeDefined();
  });

  it("renders singular cluster label correctly", () => {
    render(() => (
      <TrendsOppositionsReport
        report={makeReport({
          trends: [makeTrend({ cluster_ids: ["cluster-a"] })],
          oppositions: [],
        })}
      />
    ));

    expect(screen.getByText("1 cluster")).toBeDefined();
    expect(screen.queryByText("1 clusters")).toBeNull();
  });

  it("renders counter-positions section with side-by-side favor/against clusters", () => {
    render(() => (
      <TrendsOppositionsReport
        report={makeReport({ trends: [], oppositions: [makeOpposition()] })}
      />
    ));

    expect(screen.getByText("Counter-positions")).toBeDefined();
    expect(screen.getByText("Policy outcomes")).toBeDefined();
    expect(screen.getByText("In favor")).toBeDefined();
    expect(screen.getByText("Against")).toBeDefined();
    expect(screen.getByText("cluster-pro")).toBeDefined();
    expect(screen.getByText("cluster-con")).toBeDefined();
    expect(
      screen.getByText("Both sides repeat the same evidence but change interpretation."),
    ).toBeDefined();
  });
});
