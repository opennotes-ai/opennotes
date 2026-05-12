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
  it("renders 'Overall: OK.' for safe level with top_signals[0] as reason", () => {
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
    expect(verdict.textContent).toBe("Overall: OK.");
    expect(reason.textContent).toBe("educational context");
  });

  it("renders 'Overall: OK.' for mild level", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "mild",
          top_signals: ["minor concern noted"],
        })}
      />
    ));

    const verdict = screen.getByTestId("overall-recommendation-verdict");
    expect(verdict.textContent).toBe("Overall: OK.");
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
    expect(verdict.textContent).toBe("Overall: OK.");
    expect(reason.textContent).toBe("manually reviewed");
  });

  it("renders long top_signal verbatim", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [
            "Text moderation flags triggered, but judged to be false positives.",
          ],
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe(
      "Text moderation flags triggered, but judged to be false positives.",
    );
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

  it("renders long rationale first clause verbatim", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "Text moderation flags triggered but judged false positives, no issues found.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe(
      "Text moderation flags triggered but judged false positives",
    );
  });

  it("whitespace-only top_signals[0] falls back to rationale", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["   "],
          rationale: "Safe content verified.",
        })}
      />
    ));

    const reason = screen.getByTestId("overall-recommendation-reason");
    expect(reason.textContent).toBe("Safe content verified");
  });

  it("empty rationale and no signals returns null (card not rendered)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: [],
          rationale: "",
        })}
      />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });

  it("whitespace-only rationale and no signals returns null (card not rendered)", () => {
    render(() => (
      <OverallRecommendationCard
        recommendation={makeRecommendation({
          level: "safe",
          top_signals: ["   "],
          rationale: "   ",
        })}
      />
    ));

    expect(screen.queryByTestId("overall-recommendation-card")).toBeNull();
  });
});
