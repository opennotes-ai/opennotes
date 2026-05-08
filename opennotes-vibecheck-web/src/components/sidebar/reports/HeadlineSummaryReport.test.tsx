import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen } from "@solidjs/testing-library";
import type { ResolvedHeadline } from "~/lib/headline-fallback";
import HeadlineSummaryReport from "./HeadlineSummaryReport";

afterEach(() => {
  cleanup();
});

const SAMPLE_TEXT =
  "Conversation looks low-risk: no harmful content matches and tone is mostly neutral.";
const LONG_HEADLINE_TEXT =
  "This is a long headline summary crafted for the line-length tests to ensure the full text renders as a readable lead-in, with no truncation, no overflow clipping, and no hidden behavior that would suggest a clamped or shortened card treatment.";

type ServerHeadline = Extract<ResolvedHeadline, { source: "server" }>;
type FallbackHeadline = Extract<ResolvedHeadline, { source: "fallback" }>;

function makeHeadline(
  overrides: Partial<ResolvedHeadline> = {},
): ResolvedHeadline {
  if (overrides.source === "fallback") {
    return {
      text: SAMPLE_TEXT,
      kind: "stock",
      source: "fallback",
      unavailable_inputs: [],
      ...overrides,
    } as FallbackHeadline;
  }
  return {
    text: SAMPLE_TEXT,
    kind: "synthesized",
    source: "server",
    unavailable_inputs: [],
    ...overrides,
  } as ServerHeadline;
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

  it("exposes data-headline-kind on the section for telemetry/e2e", () => {
    render(() => (
      <HeadlineSummaryReport headline={makeHeadline({ kind: "stock" })} />
    ));
    expect(
      screen.getByTestId("headline-summary").getAttribute("data-headline-kind"),
    ).toBe("stock");
  });

  it("exposes data-headline-source on the section for telemetry/e2e", () => {
    render(() => (
      <HeadlineSummaryReport
        headline={makeHeadline({ kind: "stock", source: "server" })}
      />
    ));
    expect(
      screen
        .getByTestId("headline-summary")
        .getAttribute("data-headline-source"),
    ).toBe("server");
  });

  it("exposes source='fallback' when rendering a fallback headline", () => {
    render(() => (
      <HeadlineSummaryReport
        headline={makeHeadline({ kind: "stock", source: "fallback" })}
      />
    ));
    expect(
      screen
        .getByTestId("headline-summary")
        .getAttribute("data-headline-source"),
    ).toBe("fallback");
  });

  it("renders the full long headline text without truncation affordances", () => {
    render(() => <HeadlineSummaryReport headline={makeHeadline({ text: LONG_HEADLINE_TEXT })} />);
    const text = screen.getByTestId("headline-summary-text");
    expect(text).toBeTruthy();
    expect(text.textContent).toBe(LONG_HEADLINE_TEXT);
    const textCls = text.getAttribute("class") ?? "";
    expect(textCls).not.toMatch(/line-clamp-|text-ellipsis|whitespace-nowrap|overflow-hidden/);
  });

  it("spans the analyze page width", () => {
    render(() => <HeadlineSummaryReport headline={makeHeadline()} />);
    const sectionCls =
      screen.getByTestId("headline-summary").getAttribute("class") ?? "";
    const textCls =
      screen.getByTestId("headline-summary-text").getAttribute("class") ?? "";
    expect(sectionCls).toMatch(/\bw-full\b/);
    expect(sectionCls).not.toMatch(/max-w-prose/);
    expect(textCls).not.toMatch(/max-w-/);
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
    const buttons = screen.queryAllByRole("button");
    const nonBellButtons = buttons.filter(
      (btn) => !btn.getAttribute("aria-label")?.startsWith("Send feedback about"),
    );
    expect(nonBellButtons.length).toBe(0);
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
