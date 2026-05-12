import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import { OverallRecommendationCard } from "./OverallRecommendationCard";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

afterEach(() => {
  cleanup();
});

function makeRecommendation(
  overrides: Partial<SafetyRecommendation> = {},
): SafetyRecommendation {
  return {
    level: "safe",
    rationale: "No harmful content detected.",
    top_signals: [],
    unavailable_inputs: [],
    ...overrides,
  };
}

describe("<OverallRecommendationCard />", () => {
  it("renders 'Overall: Pass.' for safe level with top_signals[0] as reason", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["educational context"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Pass.");
    expect(reason.textContent).toBe("educational context");
  });

  it("renders 'Overall: Pass.' for mild level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern noted"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: Pass.");
  });

  it("renders 'Overall: Flag!' for unsafe level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "unsafe",
          top_signals: ["explicit harmful content found"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: Flag!");
  });

  it("renders 'Overall: Flag!' for caution level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "caution",
          top_signals: ["potentially sensitive material"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: Flag!");
  });

  it("returns null when recommendation is null and overall is absent", () => {
    render(() => (
      <OverallRecommendationCard recommendation={null} />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("returns null when recommendation is null and overall is null", () => {
    render(() => (
      <OverallRecommendationCard recommendation={null} overall={null} />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("explicit overall prop overrides derived value", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({ level: "unsafe", top_signals: ["bad content"] })}
        overall={{ verdict: "pass", reason: "manually reviewed" }}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(verdict.textContent).toBe("Overall: Pass.");
    expect(reason.textContent).toBe("manually reviewed");
  });

  it("truncates long top_signal to ≤6 words", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["one two three four five six seven eight"],
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    const words = reason.textContent?.trim().split(/\s+/) ?? [];
    expect(words.length).toBeLessThanOrEqual(6);
    expect(reason.textContent).toBe("one two three four five six");
  });

  it("falls back to rationale first clause when top_signals is empty", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "Content is safe, no issues found.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Content is safe");
  });
});
