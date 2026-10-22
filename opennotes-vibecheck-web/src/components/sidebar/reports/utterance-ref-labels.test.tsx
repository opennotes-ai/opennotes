import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@solidjs/testing-library";
import type { JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import { UtterancesProvider } from "../UtterancesContext";
import ClaimsDedupReport from "./ClaimsDedupReport";
import FlashpointReport from "./FlashpointReport";
import SafetyModerationReport from "./SafetyModerationReport";
import SubjectiveReport from "./SubjectiveReport";

type ClaimsReport = components["schemas"]["ClaimsReport"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

function anchor(utteranceId: string, position: number): UtteranceAnchor {
  return {
    utterance_id: utteranceId,
    position,
  };
}

const anchors = [
  anchor("post-0-aaa", 1),
  anchor("comment-1-bbb", 2),
  anchor("comment-2-ccc", 3),
  anchor("reply-3-ddd", 4),
];

function renderWithUtterances(children: () => JSX.Element) {
  return render(() => (
    <UtterancesProvider value={anchors}>{children()}</UtterancesProvider>
  ));
}

afterEach(() => cleanup());

describe("report utterance reference labels", () => {
  it("renders claim refs from utterance context", async () => {
    const report: ClaimsReport = {
      deduped_claims: [
        {
          canonical_text: "The policy changed.",
          category: "potentially_factual",
          occurrence_count: 2,
          author_count: 1,
          utterance_ids: ["comment-1-bbb", "reply-3-ddd"],
          chunk_refs: [
            {
              utterance_id: "comment-1-bbb",
              chunk_idx: 2,
              chunk_count: 3,
            },
            {
              utterance_id: "reply-3-ddd",
              chunk_idx: 0,
              chunk_count: 2,
            },
          ],
          representative_authors: ["author-a"],
          facts_to_verify: 0,
          supporting_facts: [
            {
              statement: "External article confirms it.",
              source_kind: "external",
              source_ref: "https://example.com/source",
            },
          ],
        },
      ],
      total_claims: 2,
      total_unique: 1,
    };

    renderWithUtterances(() => (
      <ClaimsDedupReport claimsReport={report} canJumpToUtterance={true} />
    ));

    expect(
      screen.getByTestId("deduped-claim-utterance-ref").textContent,
    ).toBe("comment #1 §3");
    expect(screen.getByText("(external)")).toBeDefined();

    await fireEvent.click(screen.getByTestId("deduped-claim-more-utterances"));

    expect(
      screen.getByTestId("deduped-claim-popover-utterance-ref").textContent,
    ).toBe("reply #1 §1");
  });

  it("renders flashpoint refs from utterance context", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "post-0-aaa",
        derailment_score: 64,
        risk_level: "Heated",
        reasoning: "rising tension",
        context_messages: 2,
      },
    ];

    renderWithUtterances(() => (
      <FlashpointReport matches={matches} canJumpToUtterance={true} />
    ));

    expect(screen.getByTestId("flashpoint-utterance-ref").textContent).toBe(
      "main post",
    );
  });

  it("renders safety fallback refs from utterance context", () => {
    const matches: HarmfulContentMatch[] = [
      {
        utterance_id: "comment-2-ccc",
        utterance_text: "",
        max_score: 0.92,
        categories: { harassment: true },
        scores: { harassment: 0.92 },
        flagged_categories: ["harassment"],
        source: "openai",
        chunk_idx: 1,
        chunk_count: 2,
      },
    ];

    renderWithUtterances(() => (
      <SafetyModerationReport matches={matches} canJumpToUtterance={true} />
    ));

    expect(screen.getByTestId("safety-utterance-ref").textContent).toBe(
      "comment #2 §2",
    );
  });

  it("renders legacy subjective refs from utterance context", () => {
    const claims: SubjectiveClaim[] = [
      {
        claim_text: "This feels unfair.",
        stance: "opposes",
        utterance_id: "comment-1-bbb",
        chunk_idx: 0,
        chunk_count: 3,
      },
    ];

    renderWithUtterances(() => (
      <SubjectiveReport claims={claims} canJumpToUtterance={true} />
    ));

    expect(
      screen.getByTestId("subjective-claim-utterance-ref").textContent,
    ).toBe("comment #1 §1");
  });
});
