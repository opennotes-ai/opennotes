import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import SafetyModerationReport from "../../../../src/components/sidebar/reports/SafetyModerationReport";
import FlashpointReport from "../../../../src/components/sidebar/reports/FlashpointReport";
import ScdReport from "../../../../src/components/sidebar/reports/ScdReport";
import ClaimsDedupReport from "../../../../src/components/sidebar/reports/ClaimsDedupReport";
import KnownMisinfoReport from "../../../../src/components/sidebar/reports/KnownMisinfoReport";
import SentimentReport from "../../../../src/components/sidebar/reports/SentimentReport";
import SubjectiveReport from "../../../../src/components/sidebar/reports/SubjectiveReport";
import type { components } from "../../../../src/lib/generated-types";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type SCDReport = components["schemas"]["SCDReport"];
type ClaimsReport = components["schemas"]["ClaimsReport"];
type FactCheckMatch = components["schemas"]["FactCheckMatch"];
type SentimentStats = components["schemas"]["SentimentStatsReport"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

afterEach(() => {
  cleanup();
});

describe("<SafetyModerationReport />", () => {
  it("renders empty-state copy when no matches are supplied", () => {
    const { container } = render(() => (
      <SafetyModerationReport matches={[]} />
    ));
    expect(screen.getByTestId("safety-empty")).toBeDefined();
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
    expect(container.innerHTML).not.toMatch(/\bborder-l-2\b/);
  });

  it("lists categories and utterance ids for each match", () => {
    const matches: HarmfulContentMatch[] = [
      {
        utterance_id: "utt-1",
        max_score: 0.82,
        flagged_categories: ["harassment", "toxicity"],
        categories: { harassment: true, toxicity: true },
        scores: {},
      },
    ];
    render(() => <SafetyModerationReport matches={matches} />);
    const categories = screen.getAllByTestId("safety-category");
    expect(categories.map((n) => n.textContent)).toEqual([
      "harassment",
      "toxicity",
    ]);
    expect(screen.getByTestId("safety-max-score").textContent).toBe("82%");
    expect(screen.getByText(/utterance utt-1/)).toBeDefined();
  });
});

describe("<FlashpointReport />", () => {
  it("falls back to neutral copy when there are no matches", () => {
    const { container } = render(() => <FlashpointReport matches={[]} />);
    expect(container.textContent).toContain("No flashpoint moments detected");
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });

  it("renders risk level and score per match", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "u-9",
        risk_level: "Heated",
        derailment_score: 72,
        reasoning: "heated exchange escalates rapidly",
        context_messages: 4,
      },
    ];
    render(() => <FlashpointReport matches={matches} />);
    expect(screen.getByTestId("flashpoint-risk-level").textContent).toBe(
      "Heated",
    );
    expect(screen.getByText(/72\/100/)).toBeDefined();
    expect(
      screen.getByText(/heated exchange escalates rapidly/),
    ).toBeDefined();
  });
});

describe("<ScdReport />", () => {
  it("surfaces the insufficient-conversation notice and no summary", () => {
    const scd: SCDReport = {
      summary: "",
      tone_labels: [],
      per_speaker_notes: {},
      insufficient_conversation: true,
    };
    const { container } = render(() => <ScdReport scd={scd} />);
    expect(screen.getByTestId("scd-insufficient")).toBeDefined();
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });

  it("renders summary, tone labels, and per-speaker notes", () => {
    const scd: SCDReport = {
      summary: "Debate with supportive tone overall",
      tone_labels: ["respectful", "focused"],
      per_speaker_notes: {
        Alice: "raises counter-evidence calmly",
        Bob: "concedes on one point",
      },
      insufficient_conversation: false,
    };
    render(() => <ScdReport scd={scd} />);
    expect(
      screen.getByText(/Debate with supportive tone overall/),
    ).toBeDefined();
    const labels = screen
      .getAllByTestId("scd-tone-label")
      .map((n) => n.textContent);
    expect(labels).toEqual(["respectful", "focused"]);
    expect(screen.getByText(/Alice/)).toBeDefined();
    expect(screen.getByText(/Bob/)).toBeDefined();
  });
});

describe("<ClaimsDedupReport />", () => {
  it("sorts deduped claims by occurrence count descending", () => {
    const claimsReport: ClaimsReport = {
      deduped_claims: [
        {
          canonical_text: "rarely said",
          occurrence_count: 1,
          author_count: 1,
          utterance_ids: ["u-1"],
          representative_authors: ["@a"],
        },
        {
          canonical_text: "often said",
          occurrence_count: 5,
          author_count: 3,
          utterance_ids: ["u-2", "u-3"],
          representative_authors: ["@b", "@c"],
        },
      ],
      total_claims: 6,
      total_unique: 2,
    };
    render(() => <ClaimsDedupReport claimsReport={claimsReport} />);
    const items = screen.getAllByTestId("deduped-claim-item");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("often said");
    expect(items[1]?.textContent).toContain("rarely said");
  });

  it("falls back to empty copy when nothing was deduped", () => {
    const claimsReport: ClaimsReport = {
      deduped_claims: [],
      total_claims: 0,
      total_unique: 0,
    };
    const { container } = render(() => (
      <ClaimsDedupReport claimsReport={claimsReport} />
    ));
    expect(container.textContent).toContain("No repeated claims identified");
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });
});

describe("<KnownMisinfoReport />", () => {
  it("groups reviews by claim text", () => {
    const matches: FactCheckMatch[] = [
      {
        claim_text: "vaccines cause X",
        textual_rating: "False",
        publisher: "factcheckers",
        review_title: "review a",
        review_url: "https://example.com/a",
      },
      {
        claim_text: "vaccines cause X",
        textual_rating: "Incorrect",
        publisher: "other",
        review_title: "review b",
        review_url: "https://example.com/b",
      },
      {
        claim_text: "separate claim",
        textual_rating: "Misleading",
        publisher: "third",
        review_title: "review c",
        review_url: "https://example.com/c",
      },
    ];
    render(() => <KnownMisinfoReport matches={matches} />);
    const items = screen.getAllByTestId("known-misinfo-item");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("vaccines cause X");
    expect(items[0]?.textContent).toContain("False");
    expect(items[0]?.textContent).toContain("Incorrect");
    expect(items[1]?.textContent).toContain("separate claim");
  });

  it("renders no-matches copy when list is empty", () => {
    const { container } = render(() => <KnownMisinfoReport matches={[]} />);
    expect(container.textContent).toContain("No known-misinformation matches");
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });
});

describe("<SentimentReport />", () => {
  it("renders positive/negative/neutral proportions and mean valence", () => {
    const stats: SentimentStats = {
      per_utterance: [],
      positive_pct: 30,
      negative_pct: 20,
      neutral_pct: 50,
      mean_valence: 0.12,
    };
    render(() => <SentimentReport stats={stats} />);
    const positive = screen.getByTestId("sentiment-positive");
    const negative = screen.getByTestId("sentiment-negative");
    const neutral = screen.getByTestId("sentiment-neutral");
    expect(positive.getAttribute("style")).toContain("width: 30%");
    expect(negative.getAttribute("style")).toContain("width: 20%");
    expect(neutral.getAttribute("style")).toContain("width: 50%");
    expect(screen.getByTestId("sentiment-mean-valence").textContent).toBe(
      "+0.12",
    );
  });

  it("clamps out-of-range percentages and keeps neutral non-negative", () => {
    const stats: SentimentStats = {
      per_utterance: [],
      positive_pct: 150,
      negative_pct: -5,
      neutral_pct: 0,
      mean_valence: Number.NaN,
    };
    render(() => <SentimentReport stats={stats} />);
    expect(
      screen.getByTestId("sentiment-positive").getAttribute("style"),
    ).toContain("width: 100%");
    expect(
      screen.getByTestId("sentiment-negative").getAttribute("style"),
    ).toContain("width: 0%");
    expect(screen.getByTestId("sentiment-mean-valence").textContent).toBe("—");
  });
});

describe("<SubjectiveReport />", () => {
  it("renders each claim with its stance label", () => {
    const claims: SubjectiveClaim[] = [
      {
        claim_text: "The policy is unfair",
        utterance_id: "u-1",
        stance: "opposes",
      },
      {
        claim_text: "This is the best outcome",
        utterance_id: "u-2",
        stance: "supports",
      },
    ];
    render(() => <SubjectiveReport claims={claims} />);
    const items = screen.getAllByTestId("subjective-claim");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("opposes");
    expect(items[0]?.textContent).toContain("The policy is unfair");
    expect(items[1]?.textContent).toContain("supports");
  });

  it("shows empty copy when no claims are present", () => {
    const { container } = render(() => <SubjectiveReport claims={[]} />);
    expect(container.textContent).toContain("No subjective claims detected");
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });
});
