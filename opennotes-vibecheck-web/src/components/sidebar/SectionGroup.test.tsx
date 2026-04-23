import { afterEach, describe, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@solidjs/testing-library";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import SectionGroup, { type SlugToSlots } from "./SectionGroup";
import Sidebar from "./Sidebar";
import type { SectionSlug, SidebarPayload } from "~/lib/api-client.server";

const TONE_SLUGS: SectionSlug[] = [
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
];

const FACTS_SLUGS: SectionSlug[] = [
  "facts_claims__dedup",
  "facts_claims__known_misinfo",
];

function makeTonePayload(): SidebarPayload {
  return {
    source_url: "https://example.com/post",
    page_title: "Example",
    page_kind: "other",
    scraped_at: "2026-04-22T00:00:00Z",
    cached: false,
    cached_at: null,
    safety: { harmful_content_matches: [] },
    tone_dynamics: {
      scd: {
        narrative: "",
        speaker_arcs: [],
        summary: "",
        tone_labels: [],
        per_speaker_notes: {},
        insufficient_conversation: true,
      },
      flashpoint_matches: [],
    },
    facts_claims: {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
      known_misinformation: [],
    },
    opinions_sentiments: {
      opinions_report: {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 0,
          negative_pct: 0,
          neutral_pct: 100,
          mean_valence: 0,
        },
        subjective_claims: [],
      },
    },
  };
}

afterEach(() => {
  cleanup();
});

describe("SectionGroup", () => {
  it("renders a 0/N counter with dim labels when all slots are pending", () => {
    const sections: SlugToSlots = {};
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    const counter = screen.getByTestId("section-group-counter");
    expect(counter.textContent).toContain("Tone/dynamics");
    expect(counter.textContent).toContain("0/2");

    for (const slug of TONE_SLUGS) {
      const label = screen.getByTestId(`slot-label-${slug}`);
      expect(label.getAttribute("data-dimmed")).toBe("true");
      expect(screen.queryByTestId(`skeleton-${slug}`)).toBeNull();
    }
  });

  it("renders a slug's content-shape skeleton when that slot is running", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: { state: "running", attempt_id: "a1" },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    expect(
      screen.getByTestId("skeleton-tone_dynamics__flashpoint"),
    ).toBeDefined();
    expect(screen.queryByTestId("skeleton-tone_dynamics__scd")).toBeNull();

    const flashLabel = screen.getByTestId("slot-label-tone_dynamics__flashpoint");
    const scdLabel = screen.getByTestId("slot-label-tone_dynamics__scd");
    expect(flashLabel.getAttribute("data-dimmed")).toBe("false");
    expect(scdLabel.getAttribute("data-dimmed")).toBe("true");
  });

  it("shows 1/2 counter with done + failed, and renders Retry for the failed slot", () => {
    const onRetry = vi.fn();
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: {
        state: "failed",
        attempt_id: "a2",
        error: "boom",
      },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
        }}
        onRetry={onRetry}
      />
    ));

    expect(screen.getByTestId("section-group-counter").textContent).toContain(
      "1/2",
    );
    expect(screen.getByTestId("fp-rendered")).toBeDefined();

    const retry = screen.getByTestId("retry-tone_dynamics__scd");
    expect(retry).toBeDefined();
    expect(
      screen.getByText(/Couldn't run this analysis/i),
    ).toBeDefined();
  });

  it("invokes onRetry with the slug when Retry is clicked", async () => {
    const onRetry = vi.fn();
    const sections: SlugToSlots = {
      facts_claims__dedup: {
        state: "failed",
        attempt_id: "a1",
        error: "boom",
      },
      facts_claims__known_misinfo: { state: "pending", attempt_id: "" },
    };
    render(() => (
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={sections}
        render={{}}
        onRetry={onRetry}
      />
    ));

    await fireEvent.click(screen.getByTestId("retry-facts_claims__dedup"));
    expect(onRetry).toHaveBeenCalledWith("facts_claims__dedup");
  });

  it("shows full counter and no skeletons when every slot is done", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "a1",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: {
        state: "done",
        attempt_id: "a2",
        data: {
          narrative: "",
          speaker_arcs: [],
          summary: "done",
          tone_labels: [],
          per_speaker_notes: {},
          insufficient_conversation: false,
        },
      },
    };
    render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => <div data-testid="fp-rendered" />,
          tone_dynamics__scd: () => <div data-testid="scd-rendered" />,
        }}
      />
    ));

    expect(screen.getByTestId("section-group-counter").textContent).toContain(
      "2/2",
    );
    expect(
      screen.queryByTestId("skeleton-tone_dynamics__flashpoint"),
    ).toBeNull();
    expect(screen.queryByTestId("skeleton-tone_dynamics__scd")).toBeNull();
    expect(screen.getByTestId("fp-rendered")).toBeDefined();
    expect(screen.getByTestId("scd-rendered")).toBeDefined();
  });

  it("wraps done content in a reveal wrapper carrying the slot attempt id", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "attempt-xyz",
        data: { flashpoint_matches: [] },
      },
      tone_dynamics__scd: { state: "pending", attempt_id: "" },
    };
    const { container } = render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{
          tone_dynamics__flashpoint: () => (
            <div data-testid="fp-rendered">flash</div>
          ),
        }}
      />
    ));

    const reveal = container.querySelector<HTMLDivElement>(".section-reveal");
    expect(reveal).not.toBeNull();
    expect(reveal?.getAttribute("data-slot-attempt-id")).toBe("attempt-xyz");
  });

  it("does not introduce left-stripe borders on cluster containers", () => {
    const sections: SlugToSlots = {
      tone_dynamics__flashpoint: { state: "running", attempt_id: "a1" },
      tone_dynamics__scd: { state: "running", attempt_id: "a2" },
    };
    const { container } = render(() => (
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={sections}
        render={{}}
      />
    ));

    const group = container.querySelector(
      '[data-testid="section-group-Tone/dynamics"]',
    );
    expect(group).not.toBeNull();
    const html = group?.outerHTML ?? "";
    expect(html).not.toMatch(/\bborder-l\b/);
    expect(html).not.toMatch(/\bborder-l-2\b/);
  });
});

describe("Sidebar", () => {
  it("renders all four named clusters with counters when sections is empty", () => {
    render(() => <Sidebar sections={{}} />);

    const aside = screen.getByTestId("analysis-sidebar");
    expect(aside.getAttribute("aria-live")).toBe("polite");

    const counters = screen.getAllByTestId("section-group-counter");
    expect(counters).toHaveLength(4);

    const texts = counters.map((n) => n.textContent ?? "");
    expect(texts.some((t) => t.startsWith("Safety"))).toBe(true);
    expect(texts.some((t) => t.startsWith("Tone/dynamics"))).toBe(true);
    expect(texts.some((t) => t.startsWith("Facts/claims"))).toBe(true);
    expect(texts.some((t) => t.startsWith("Opinions/sentiments"))).toBe(true);
  });

  it("uses middot separator and integer N/M in counter labels", () => {
    render(() => <Sidebar sections={{}} />);
    const counters = screen.getAllByTestId("section-group-counter");
    for (const c of counters) {
      const text = c.textContent ?? "";
      expect(text).toMatch(/\s·\s\d+\/\d+/);
    }
  });

  it("synthesizes a fully-done sections map from payload when sections is absent", () => {
    const payload = makeTonePayload();
    render(() => <Sidebar payload={payload} />);

    const counters = screen.getAllByTestId("section-group-counter");
    const texts = counters.map((n) => n.textContent ?? "");
    expect(texts.find((t) => t.startsWith("Safety"))).toContain("1/1");
    expect(texts.find((t) => t.startsWith("Tone/dynamics"))).toContain("2/2");
    expect(texts.find((t) => t.startsWith("Facts/claims"))).toContain("2/2");
    expect(texts.find((t) => t.startsWith("Opinions/sentiments"))).toContain(
      "2/2",
    );

    expect(screen.queryByTestId("skeleton-safety__moderation")).toBeNull();
    expect(
      screen.queryByTestId("skeleton-tone_dynamics__flashpoint"),
    ).toBeNull();
  });

  it("omits left-stripe border classes anywhere in the rendered sidebar", () => {
    const { container } = render(() => (
      <Sidebar
        sections={{
          safety__moderation: { state: "running", attempt_id: "a1" },
          tone_dynamics__flashpoint: { state: "running", attempt_id: "a2" },
          tone_dynamics__scd: { state: "running", attempt_id: "a3" },
          facts_claims__dedup: { state: "running", attempt_id: "a4" },
          facts_claims__known_misinfo: { state: "running", attempt_id: "a5" },
          opinions_sentiments__sentiment: { state: "running", attempt_id: "a6" },
          opinions_sentiments__subjective: { state: "running", attempt_id: "a7" },
        }}
      />
    ));

    const html = container.innerHTML;
    expect(html).not.toMatch(/\bborder-l\b/);
    expect(html).not.toMatch(/\bborder-l-2\b/);
  });
});

describe("Sidebar (done slots, per-slug reports)", () => {
  function doneSections(): SlugToSlots {
    return {
      safety__moderation: {
        state: "done",
        attempt_id: "s-safety",
        data: {
          harmful_content_matches: [
            {
              utterance_id: "u-safety",
              max_score: 0.91,
              flagged_categories: ["harassment"],
              scores: {},
            },
          ],
        },
      },
      tone_dynamics__flashpoint: {
        state: "done",
        attempt_id: "s-flash",
        data: {
          flashpoint_matches: [
            {
              utterance_id: "u-flash",
              risk_level: "medium",
              derailment_score: 55,
              reasoning: "tone shifts sharply",
            },
          ],
        },
      },
      tone_dynamics__scd: {
        state: "done",
        attempt_id: "s-scd",
        data: {
          scd: {
            narrative: "",
            speaker_arcs: [],
            summary: "scd summary text",
            tone_labels: ["curious"],
            per_speaker_notes: { Alice: "opens with evidence" },
            insufficient_conversation: false,
          },
        },
      },
      facts_claims__dedup: {
        state: "done",
        attempt_id: "s-dedup",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "canonical claim text",
                occurrence_count: 3,
                author_count: 2,
                utterance_ids: ["u-1"],
              },
            ],
            total_claims: 3,
            total_unique: 1,
          },
        },
      },
      facts_claims__known_misinfo: {
        state: "done",
        attempt_id: "s-known",
        data: {
          known_misinformation: [
            {
              claim_text: "known-misinfo-claim",
              textual_rating: "False",
              publisher: "factcheckers",
              review_url: "https://example.com/r",
            },
          ],
        },
      },
      opinions_sentiments__sentiment: {
        state: "done",
        attempt_id: "s-sent",
        data: {
          sentiment_stats: {
            per_utterance: [],
            positive_pct: 40,
            negative_pct: 10,
            neutral_pct: 50,
            mean_valence: 0.25,
          },
        },
      },
      opinions_sentiments__subjective: {
        state: "done",
        attempt_id: "s-subj",
        data: {
          subjective_claims: [
            { claim_text: "subjective-claim-one", stance: "positive" },
          ],
        },
      },
    };
  }

  it("renders each slug's own report and none of its siblings' content", () => {
    render(() => <Sidebar sections={doneSections()} />);

    expect(
      screen.getByTestId("report-safety__moderation"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-tone_dynamics__flashpoint"),
    ).toBeDefined();
    expect(screen.getByTestId("report-tone_dynamics__scd")).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__dedup"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__known_misinfo"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__sentiment"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__subjective"),
    ).toBeDefined();

    const flashReport = screen.getByTestId(
      "report-tone_dynamics__flashpoint",
    );
    expect(flashReport.textContent).not.toContain("scd summary text");
    const scdReport = screen.getByTestId("report-tone_dynamics__scd");
    expect(scdReport.textContent).not.toContain("tone shifts sharply");

    const dedupReport = screen.getByTestId("report-facts_claims__dedup");
    expect(dedupReport.textContent).not.toContain("known-misinfo-claim");
    const knownReport = screen.getByTestId(
      "report-facts_claims__known_misinfo",
    );
    expect(knownReport.textContent).not.toContain("canonical claim text");

    const sentimentReport = screen.getByTestId(
      "report-opinions_sentiments__sentiment",
    );
    expect(sentimentReport.textContent).not.toContain(
      "subjective-claim-one",
    );
    const subjectiveReport = screen.getByTestId(
      "report-opinions_sentiments__subjective",
    );
    expect(subjectiveReport.textContent).not.toContain(
      "mean valence",
    );
  });

  it("renders done slots without any left-stripe border classes", () => {
    const { container } = render(() => <Sidebar sections={doneSections()} />);
    const html = container.innerHTML;
    expect(html).not.toMatch(/\bborder-l\b/);
    expect(html).not.toMatch(/\bborder-l-2\b/);
  });

  it("synthesizes identical report test ids when driven by payload only", () => {
    const payload: SidebarPayload = {
      source_url: "https://example.com/post",
      page_title: "Example",
      page_kind: "other",
      scraped_at: "2026-04-22T00:00:00Z",
      cached: false,
      cached_at: null,
      safety: {
        harmful_content_matches: [
          {
            utterance_id: "u-p-safety",
            max_score: 0.5,
            flagged_categories: ["toxicity"],
            categories: { toxicity: true },
            scores: {},
          },
        ],
      },
      tone_dynamics: {
        scd: {
          narrative: "",
          speaker_arcs: [],
          summary: "payload summary",
          tone_labels: [],
          per_speaker_notes: {},
          insufficient_conversation: false,
        },
        flashpoint_matches: [],
      },
      facts_claims: {
        claims_report: {
          deduped_claims: [],
          total_claims: 0,
          total_unique: 0,
        },
        known_misinformation: [],
      },
      opinions_sentiments: {
        opinions_report: {
          sentiment_stats: {
            per_utterance: [],
            positive_pct: 10,
            negative_pct: 10,
            neutral_pct: 80,
            mean_valence: 0,
          },
          subjective_claims: [],
        },
      },
    };
    const { container } = render(() => <Sidebar payload={payload} />);
    expect(
      screen.getByTestId("report-safety__moderation"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-tone_dynamics__flashpoint"),
    ).toBeDefined();
    expect(screen.getByTestId("report-tone_dynamics__scd")).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__dedup"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-facts_claims__known_misinfo"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__sentiment"),
    ).toBeDefined();
    expect(
      screen.getByTestId("report-opinions_sentiments__subjective"),
    ).toBeDefined();

    const html = container.innerHTML;
    expect(html).not.toMatch(/\bborder-l\b/);
    expect(html).not.toMatch(/\bborder-l-2\b/);
  });
});

describe("app.css motion rules", () => {
  it("defines .skeleton-pulse and .section-reveal keyframes", () => {
    const appCssPath = resolve(process.cwd(), "src/app.css");
    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).toMatch(/\.skeleton-pulse\b/);
    expect(appCss).toMatch(/\.section-reveal\b/);
    expect(appCss).toMatch(/@keyframes\s+skeleton-pulse-kf\b/);
    expect(appCss).toMatch(/@keyframes\s+section-reveal-kf\b/);
  });
});
