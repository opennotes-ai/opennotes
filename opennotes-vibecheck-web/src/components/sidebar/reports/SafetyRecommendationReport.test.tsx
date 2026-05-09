import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import SafetyRecommendationReport from "./SafetyRecommendationReport";

vi.mock("../../../lib/feedback-client", () => ({
  openFeedback: vi.fn().mockResolvedValue({ id: "test-id" }),
  submitFeedback: vi.fn().mockResolvedValue(undefined),
  submitFeedbackCombined: vi.fn().mockResolvedValue({ id: "combined-id" }),
  FeedbackApiError: class FeedbackApiError extends Error {
    constructor(
      public status: number,
      public body: unknown,
      message?: string,
    ) {
      super(message ?? `Feedback API error (${status})`);
      this.name = "FeedbackApiError";
    }
  },
}));

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

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
    const buttons = screen.queryAllByRole("button");
    const nonBellButtons = buttons.filter(
      (btn) => !btn.getAttribute("aria-label")?.startsWith("Send feedback about"),
    );
    expect(nonBellButtons.length).toBe(0);
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

  it("renders the mild badge with the light amber palette", () => {
    render(() => (
      <SafetyRecommendationReport
        recommendation={makeRecommendation({ level: "mild" })}
      />
    ));
    const badge = screen.getByTestId("safety-recommendation-level");
    expect(badge.textContent).toBe("mild");
    expect(badge.className).toContain("bg-yellow-100");
    expect(badge.className).toContain("text-yellow-800");
    expect(badge.className).toContain("dark:text-yellow-300");
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

  it("renders a FeedbackBell with the correct bell_location aria-label", () => {
    render(() => (
      <SafetyRecommendationReport recommendation={makeRecommendation()} />
    ));
    const bell = screen.getByRole("button", {
      name: "Send feedback about card:safety-recommendation",
    });
    expect(bell).toBeTruthy();
  });

  it("outer wrapper has pb-8 and pr-8 so the bell sits in the bottom-right corner", () => {
    render(() => (
      <SafetyRecommendationReport recommendation={makeRecommendation()} />
    ));
    const wrapper = screen.getByTestId("safety-recommendation-report");
    expect(wrapper.className).toContain("pb-8");
    expect(wrapper.className).toContain("pr-8");
  });
});
