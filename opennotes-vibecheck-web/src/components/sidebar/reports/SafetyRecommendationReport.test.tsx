import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import SafetyRecommendationReport from "./SafetyRecommendationReport";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

afterEach(() => {
  cleanup();
});

const LONG_RATIONALE =
  "This conversation includes multiple harmful-content matches across several " +
  "utterances. Reviewers should treat the thread as elevated risk and consult " +
  "the linked policy guidance before taking action on any individual message.";

function makeRecommendation(
  overrides: Partial<SafetyRecommendation> = {},
): SafetyRecommendation {
  return {
    level: "caution",
    rationale: LONG_RATIONALE,
    top_signals: [],
    unavailable_inputs: [],
    ...overrides,
  };
}

describe("SafetyRecommendationReport", () => {
  it("renders nothing when recommendation is null", () => {
    render(() => <SafetyRecommendationReport recommendation={null} />);
    expect(
      screen.queryByTestId("safety-recommendation-report"),
    ).toBeNull();
  });

  it("renders rationale as a plain paragraph (no expandable affordance)", () => {
    render(() => (
      <SafetyRecommendationReport recommendation={makeRecommendation()} />
    ));
    const rationale = screen.getByTestId("safety-recommendation-rationale");
    expect(rationale.tagName.toLowerCase()).toBe("p");
    expect(rationale.textContent).toBe(LONG_RATIONALE);
    expect(rationale.getAttribute("data-truncated")).toBeNull();
    const cls = rationale.getAttribute("class") ?? "";
    expect(cls).not.toMatch(/line-clamp-/);
    expect(screen.queryAllByRole("button").length).toBe(0);
  });

  it("renders the recommendation level badge", () => {
    render(() => (
      <SafetyRecommendationReport
        recommendation={makeRecommendation({ level: "unsafe" })}
      />
    ));
    expect(screen.getByTestId("safety-recommendation-level").textContent).toBe(
      "unsafe",
    );
  });

  it("renders top signals (capped at 3) and a +N more indicator", () => {
    render(() => (
      <SafetyRecommendationReport
        recommendation={makeRecommendation({
          top_signals: ["a", "b", "c", "d", "e"],
        })}
      />
    ));
    const items = screen
      .getByTestId("safety-recommendation-report")
      .querySelectorAll("li");
    expect(items.length).toBe(4);
    expect(items[3]?.textContent).toBe("+2 more");
  });
});
