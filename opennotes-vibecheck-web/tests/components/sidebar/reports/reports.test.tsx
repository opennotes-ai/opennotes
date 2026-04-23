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
  it("renders a conversational empty state when matches is empty", () => {
    const { container } = render(() => <FlashpointReport matches={[]} />);

    const empty = screen.getByTestId("flashpoint-empty");
    expect(empty).not.toBeNull();
    expect(empty.textContent).toMatch(/even-keeled/i);
    expect(screen.queryByText(/flashpoint moments detected/i)).toBeNull();
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });

  it("renders empty state when matches is undefined (defensive path)", () => {
    render(() => (
      // @ts-expect-error: testing the defensive `props.matches ?? []` path
      <FlashpointReport matches={undefined} />
    ));

    const empty = screen.getByTestId("flashpoint-empty");
    expect(empty).not.toBeNull();
    expect(empty.textContent).toMatch(/even-keeled/i);
  });

  it("renders empty state when matches is null (defensive path)", () => {
    render(() => (
      // @ts-expect-error: testing the defensive `props.matches ?? []` path
      <FlashpointReport matches={null} />
    ));

    const empty = screen.getByTestId("flashpoint-empty");
    expect(empty).not.toBeNull();
    expect(empty.textContent).toMatch(/even-keeled/i);
  });

  it("renders a single Hostile match with sharp-clash headline", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "14",
        derailment_score: 88,
        risk_level: "Hostile",
        reasoning: "personal attack and name-calling",
        context_messages: 3,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headline = screen.getByTestId("flashpoint-headline");
    expect(headline.textContent).toMatch(/sharp clash/i);
    expect(headline.textContent).toMatch(/turn 14/);
    expect(headline.textContent).toMatch(/high risk/i);
  });

  it("renders a single Heated match with heated-exchange headline", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "7",
        derailment_score: 65,
        risk_level: "Heated",
        reasoning: "rising frustration on both sides",
        context_messages: 2,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headline = screen.getByTestId("flashpoint-headline");
    expect(headline.textContent).toMatch(/heated exchange/i);
    expect(headline.textContent).toMatch(/turn 7/);
    expect(headline.textContent).toMatch(/moderate risk/i);
  });

  it("renders a single Low Risk match with brief-tense-moment headline", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "3",
        derailment_score: 22,
        risk_level: "Low Risk",
        reasoning: "minor disagreement, quickly resolved",
        context_messages: 2,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headline = screen.getByTestId("flashpoint-headline");
    expect(headline.textContent).toMatch(/brief tense moment/i);
    expect(headline.textContent).toMatch(/turn 3/);
    expect(headline.textContent).toMatch(/low risk/i);
  });

  it("renders a single Guarded match with brief-tense-moment phrase and low-risk qualifier", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "5",
        derailment_score: 25,
        risk_level: "Guarded",
        reasoning: "minor friction surfacing",
        context_messages: 2,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headline = screen.getByTestId("flashpoint-headline");
    expect(headline.textContent).toMatch(/brief tense moment/i);
    expect(headline.textContent).toMatch(/turn 5/);
    expect(headline.textContent).toMatch(/low risk/i);
  });

  it("renders a single Dangerous match with severe-risk qualifier", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "21",
        derailment_score: 97,
        risk_level: "Dangerous",
        reasoning: "explicit threats exchanged",
        context_messages: 4,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headline = screen.getByTestId("flashpoint-headline");
    expect(headline.textContent).toMatch(/dangerous flashpoint/i);
    expect(headline.textContent).toMatch(/turn 21/);
    expect(headline.textContent).toMatch(/severe risk/i);
  });

  it("renders the derailment score in a secondary muted line", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "9",
        derailment_score: 73,
        risk_level: "Heated",
        reasoning: "tone is climbing",
        context_messages: 2,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const score = screen.getByTestId("flashpoint-score");
    expect(score.textContent).toMatch(/derailment ~73\/100/);
  });

  it("renders the reasoning paragraph beneath the headline", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "12",
        derailment_score: 60,
        risk_level: "Heated",
        reasoning: "sarcasm hardening into outright dismissal",
        context_messages: 3,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const reasoning = screen.getByTestId("flashpoint-reasoning");
    expect(reasoning.textContent).toMatch(
      /sarcasm hardening into outright dismissal/,
    );
    expect(reasoning.className).toMatch(/line-clamp-2/);
  });

  it("renders multiple matches in input order", () => {
    const matches: FlashpointMatch[] = [
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "4",
        derailment_score: 30,
        risk_level: "Guarded",
        reasoning: "first wobble",
        context_messages: 2,
      },
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "11",
        derailment_score: 70,
        risk_level: "Heated",
        reasoning: "second escalation",
        context_messages: 3,
      },
      {
        scan_type: "conversation_flashpoint",
        utterance_id: "18",
        derailment_score: 90,
        risk_level: "Hostile",
        reasoning: "third break",
        context_messages: 4,
      },
    ];

    render(() => <FlashpointReport matches={matches} />);

    const headlines = screen
      .getAllByTestId("flashpoint-headline")
      .map((el) => el.textContent ?? "");
    expect(headlines).toHaveLength(3);
    expect(headlines[0]).toMatch(/turn 4/);
    expect(headlines[1]).toMatch(/turn 11/);
    expect(headlines[2]).toMatch(/turn 18/);
  });
});

function makeScd(overrides: Partial<SCDReport> = {}): SCDReport {
  return {
    narrative: "",
    summary: "",
    tone_labels: [],
    per_speaker_notes: {},
    speaker_arcs: [],
    insufficient_conversation: false,
    ...overrides,
  };
}

describe("<ScdReport />", () => {
  it("renders narrative when non-empty", () => {
    const scd = makeScd({
      narrative:
        "Alice opens warmly, Bob pushes back, and the thread cools by the end.",
    });

    render(() => <ScdReport scd={scd} />);

    const narrative = screen.getByTestId("scd-narrative");
    expect(narrative.textContent).toMatch(/Alice opens warmly/);
    expect(screen.queryByTestId("scd-insufficient")).toBeNull();
  });

  it("falls back to summary when narrative is empty and insufficient_conversation is false", () => {
    const scd = makeScd({
      narrative: "",
      summary: "Summary fallback paragraph for back-compat.",
    });

    render(() => <ScdReport scd={scd} />);

    const narrative = screen.getByTestId("scd-narrative");
    expect(narrative.textContent).toMatch(/Summary fallback paragraph/);
  });

  it("renders insufficient placeholder when insufficient_conversation is true", () => {
    const scd = makeScd({
      narrative: "ignored when insufficient",
      summary: "ignored too",
      tone_labels: ["combative"],
      speaker_arcs: [{ speaker: "alice", note: "n/a" }],
      insufficient_conversation: true,
    });

    const { container } = render(() => <ScdReport scd={scd} />);

    const placeholder = screen.getByTestId("scd-insufficient");
    expect(placeholder.textContent).toMatch(/back-and-forth/i);
    expect(screen.queryByTestId("scd-narrative")).toBeNull();
    expect(screen.queryByTestId("scd-speaker-arc")).toBeNull();
    expect(screen.queryByTestId("scd-tone-label")).toBeNull();
    expect(container.innerHTML).not.toMatch(/\bborder-l\b/);
  });

  it("renders speaker_arcs with range badge when utterance_id_range present", () => {
    const scd = makeScd({
      narrative: "narrative present",
      speaker_arcs: [
        {
          speaker: "alice",
          note: "gets defensive around the middle of the thread",
          utterance_id_range: [3, 7],
        },
      ],
    });

    render(() => <ScdReport scd={scd} />);

    const arc = screen.getByTestId("scd-speaker-arc");
    expect(arc.textContent).toMatch(/alice/);
    expect(arc.textContent).toMatch(/gets defensive/);

    const range = screen.getByTestId("scd-arc-range");
    expect(range.textContent).toMatch(/turns 3-7/);
    expect(range.getAttribute("aria-label")).toMatch(/turns 3-7/);
  });

  it("renders speaker_arcs without range badge when utterance_id_range is null", () => {
    const scd = makeScd({
      narrative: "narrative present",
      speaker_arcs: [
        {
          speaker: "bob",
          note: "stays measured throughout",
          utterance_id_range: null,
        },
      ],
    });

    render(() => <ScdReport scd={scd} />);

    const arc = screen.getByTestId("scd-speaker-arc");
    expect(arc.textContent).toMatch(/bob/);
    expect(arc.textContent).toMatch(/stays measured/);
    expect(screen.queryByTestId("scd-arc-range")).toBeNull();
  });

  it("renders multiple speaker_arcs in input order", () => {
    const scd = makeScd({
      narrative: "narrative present",
      speaker_arcs: [
        { speaker: "alice", note: "opens warmly" },
        { speaker: "bob", note: "pushes back" },
        { speaker: "carol", note: "tries to bridge" },
      ],
    });

    render(() => <ScdReport scd={scd} />);

    const arcs = screen
      .getAllByTestId("scd-speaker-arc")
      .map((el) => el.textContent ?? "");
    expect(arcs).toHaveLength(3);
    expect(arcs[0]).toMatch(/alice/);
    expect(arcs[1]).toMatch(/bob/);
    expect(arcs[2]).toMatch(/carol/);
  });

  it("renders tone_labels as chips", () => {
    const scd = makeScd({
      narrative: "narrative present",
      tone_labels: ["combative", "dismissive"],
    });

    render(() => <ScdReport scd={scd} />);

    const labels = screen
      .getAllByTestId("scd-tone-label")
      .map((el) => el.textContent);
    expect(labels).toEqual(["combative", "dismissive"]);
  });

  it("renders nothing for arcs when speaker_arcs is undefined", () => {
    const scd: SCDReport = {
      narrative: "narrative present",
      summary: "",
      tone_labels: [],
      per_speaker_notes: {},
      insufficient_conversation: false,
    };

    render(() => <ScdReport scd={scd} />);

    expect(screen.queryByTestId("scd-speaker-arc")).toBeNull();
  });

  it("uses no academic words in default insufficient copy", () => {
    const scd = makeScd({ insufficient_conversation: true });

    render(() => <ScdReport scd={scd} />);

    const placeholder = screen.getByTestId("scd-insufficient");
    const text = placeholder.textContent ?? "";
    expect(text).not.toMatch(/SCD/);
    expect(text).not.toMatch(/utterance/i);
  });

  it("uses no academic words in body copy for a populated SCDReport", () => {
    const scd = makeScd({
      narrative: "Alice and Bob trade jabs before settling down.",
      tone_labels: ["combative"],
      speaker_arcs: [
        {
          speaker: "alice",
          note: "softens after the midpoint",
          utterance_id_range: [4, 9],
        },
      ],
    });

    const { container } = render(() => <ScdReport scd={scd} />);

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/SCD/);
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

  it("honors backend neutral_pct as authoritative (does not derive from positive+negative)", () => {
    const stats: SentimentStats = {
      per_utterance: [],
      positive_pct: 30,
      negative_pct: 20,
      neutral_pct: 10,
      mean_valence: 0,
    };
    render(() => <SentimentReport stats={stats} />);
    expect(
      screen.getByTestId("sentiment-neutral").getAttribute("style"),
    ).toContain("width: 10%");
  });

  it("clamps neutral_pct to [0, 100]", () => {
    const stats: SentimentStats = {
      per_utterance: [],
      positive_pct: 0,
      negative_pct: 0,
      neutral_pct: 250,
      mean_valence: 0,
    };
    render(() => <SentimentReport stats={stats} />);
    expect(
      screen.getByTestId("sentiment-neutral").getAttribute("style"),
    ).toContain("width: 100%");
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
