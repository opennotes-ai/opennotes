import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import HeadlineSummaryReport from "./HeadlineSummaryReport";

type HeadlineSummary = components["schemas"]["HeadlineSummary"];

afterEach(() => {
  cleanup();
});

const SAMPLE_TEXT =
  "Conversation looks low-risk: no harmful content matches and tone is mostly neutral.";

function makeHeadline(
  overrides: Partial<HeadlineSummary> = {},
): HeadlineSummary {
  return {
    text: SAMPLE_TEXT,
    kind: "synthesized",
    unavailable_inputs: [],
    ...overrides,
  };
}

describe("HeadlineSummaryReport", () => {
  it("renders nothing when headline is null", () => {
    render(() => <HeadlineSummaryReport headline={null} />);
    expect(screen.queryByTestId("headline-summary")).toBeNull();
    expect(screen.queryByTestId("headline-summary-text")).toBeNull();
  });

  it("renders the headline text and section testid when populated", () => {
    render(() => <HeadlineSummaryReport headline={makeHeadline()} />);
    expect(screen.getByTestId("headline-summary")).toBeTruthy();
    const text = screen.getByTestId("headline-summary-text");
    expect(text.tagName.toLowerCase()).toBe("p");
    expect(text.textContent).toBe(SAMPLE_TEXT);
  });

  it("renders identical text for kind='stock' and kind='synthesized'", () => {
    const { unmount } = render(() => (
      <HeadlineSummaryReport headline={makeHeadline({ kind: "stock" })} />
    ));
    const stockText =
      screen.getByTestId("headline-summary-text").textContent ?? "";
    unmount();
    cleanup();
    render(() => (
      <HeadlineSummaryReport
        headline={makeHeadline({ kind: "synthesized" })}
      />
    ));
    const synthesizedText =
      screen.getByTestId("headline-summary-text").textContent ?? "";
    expect(stockText).toBe(synthesizedText);
    expect(stockText).toBe(SAMPLE_TEXT);
  });

  it("renders no role='button' (no ExpandableText affordance)", () => {
    render(() => <HeadlineSummaryReport headline={makeHeadline()} />);
    expect(screen.queryAllByRole("button").length).toBe(0);
  });

  it("renders no element with data-truncated (no read-more chrome)", () => {
    render(() => <HeadlineSummaryReport headline={makeHeadline()} />);
    const section = screen.getByTestId("headline-summary");
    expect(section.querySelector("[data-truncated]")).toBeNull();
    const text = screen.getByTestId("headline-summary-text");
    expect(text.getAttribute("data-truncated")).toBeNull();
    const cls = text.getAttribute("class") ?? "";
    expect(cls).not.toMatch(/line-clamp-/);
  });
});
