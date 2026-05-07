import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import type { components } from "~/lib/generated-types";
import HighlightsReport from "./HighlightsReport";

type OpinionsHighlightsReport = components["schemas"]["OpinionsHighlightsReport"];
type OpinionsHighlight = components["schemas"]["OpinionsHighlight"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

const makeHighlight = (
  overrides: Partial<OpinionsHighlight> = {},
): OpinionsHighlight => ({
  cluster: {
    canonical_text: "Repeated framing around policy impact.",
    category: "subjective",
    occurrence_count: 4,
    author_count: 3,
    utterance_ids: ["u-1", "u-2"],
    representative_authors: ["author-a"],
    facts_to_verify: 0,
  },
  crossed_scaled_threshold: true,
  ...overrides,
});

const makeReport = (
  overrides: Partial<OpinionsHighlightsReport> = {},
): OpinionsHighlightsReport => ({
  highlights: [],
  threshold: {
    total_authors: 4,
    total_utterances: 8,
    min_authors_required: 2,
    min_occurrences_required: 2,
  },
  fallback_engaged: false,
  floor_eligible_count: 0,
  total_input_count: 0,
  ...overrides,
});

const makeLegacyClaim = (
  overrides: Partial<SubjectiveClaim> = {},
): SubjectiveClaim => ({
  claim_text: "I think this policy is unfair.",
  stance: "opposes",
  utterance_id: "legacy-1",
  ...overrides,
});

afterEach(() => cleanup());

describe("HighlightsReport", () => {
  it("renders nothing when report is null and legacy claims are empty", () => {
    render(() => <HighlightsReport report={null} legacySubjectiveClaims={[]} />);
    expect(
      screen.queryByTestId("report-opinions_sentiments__highlights"),
    ).toBeNull();
    expect(
      screen.queryByTestId("report-opinions_sentiments__subjective"),
    ).toBeNull();
  });

  it("renders legacy SubjectiveReport when report is null and legacy claims exist", () => {
    render(() => (
      <HighlightsReport
        report={null}
        legacySubjectiveClaims={[makeLegacyClaim()]}
      />
    ));
    expect(
      screen.getByTestId("report-opinions_sentiments__subjective"),
    ).toBeDefined();
    expect(screen.getByText("I think this policy is unfair.")).toBeDefined();
  });

  it("renders highlights text with author and occurrence badges", () => {
    render(() => (
      <HighlightsReport report={makeReport({ highlights: [makeHighlight()] })} />
    ));
    expect(
      screen.getByTestId("report-opinions_sentiments__highlights"),
    ).toBeDefined();
    expect(screen.getByText("Repeated framing around policy impact.")).toBeDefined();
    expect(screen.getByText("3 authors")).toBeDefined();
    expect(screen.getByText("4 occurrences")).toBeDefined();
  });

  it("shows limited evidence tag only when fallback_engaged is true", () => {
    render(() => (
      <HighlightsReport report={makeReport({ fallback_engaged: true })} />
    ));
    expect(screen.getByText(/limited evidence/i)).toBeDefined();

    cleanup();
    render(() => <HighlightsReport report={makeReport({ fallback_engaged: false })} />);
    expect(screen.queryByText(/limited evidence/i)).toBeNull();
  });

  it("does not render legacy subjective claims when a highlights report exists", () => {
    render(() => (
      <HighlightsReport
        report={makeReport({ highlights: [] })}
        legacySubjectiveClaims={[makeLegacyClaim()]}
      />
    ));
    expect(
      screen.getByTestId("report-opinions_sentiments__highlights"),
    ).toBeDefined();
    expect(screen.queryByTestId("report-opinions_sentiments__subjective")).toBeNull();
    expect(screen.queryByText("I think this policy is unfair.")).toBeNull();
  });

  it("wires utterance click using the first utterance id", async () => {
    const onUtteranceClick = vi.fn();
    render(() => (
      <HighlightsReport
        report={makeReport({ highlights: [makeHighlight()] })}
        onUtteranceClick={onUtteranceClick}
        canJumpToUtterance={true}
      />
    ));
    await fireEvent.click(screen.getByTestId("highlight-utterance-ref"));
    expect(onUtteranceClick).toHaveBeenCalledWith("u-1");
  });
});
