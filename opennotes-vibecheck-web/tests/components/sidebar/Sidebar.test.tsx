import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import Sidebar from "~/components/sidebar/Sidebar";
import type { JobState, SidebarPayload } from "~/lib/api-client.server";
import { makeEmptyScd } from "~/lib/sidebar-defaults";

afterEach(() => {
  cleanup();
});

const SECTION_SLUGS = [
  "safety__moderation",
  "safety__web_risk",
  "safety__image_moderation",
  "safety__video_moderation",
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
  "facts_claims__dedup",
  "facts_claims__evidence",
  "facts_claims__premises",
  "facts_claims__known_misinfo",
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
  "opinions_sentiments__trends_oppositions",
] as const;

function makePayload(overrides: Partial<SidebarPayload> = {}): SidebarPayload {
  return {
    source_url: "https://news.example.com/a",
    page_title: "Example",
    page_kind: "article",
    scraped_at: "2026-04-22T00:00:00Z",
    cached: false,
    cached_at: null,
    safety: { harmful_content_matches: [] },
    web_risk: { findings: [], urls_checked: 0 },
    image_moderation: { matches: [] },
    video_moderation: { matches: [] },
    tone_dynamics: {
      scd: makeEmptyScd(),
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
          neutral_pct: 0,
          mean_valence: 0,
        },
        subjective_claims: [],
      },
      trends_oppositions: {
        trends: [],
        oppositions: [],
        input_cluster_count: 0,
        skipped_for_cap: 0,
      },
    },
    ...overrides,
  } as SidebarPayload;
}

function getSlotState(slug: string): string | null {
  const el = screen.queryByTestId(`slot-${slug}`);
  return el?.getAttribute("data-slot-state") ?? null;
}

describe("<Sidebar /> payload synthesis fallback", () => {
  it("renders all slots as done when sections is undefined and payload is provided (cache-hit shape)", () => {
    render(() => (
      <Sidebar sections={undefined} payload={makePayload()} payloadComplete={true} />
    ));

    for (const slug of SECTION_SLUGS) {
      expect(getSlotState(slug)).toBe("done");
    }
  });

  it("renders all slots as done when sections is an empty object and payload is provided (real cache-hit backend shape)", () => {
    const emptySections = {} as unknown as JobState["sections"];

    render(() => (
      <Sidebar sections={emptySections} payload={makePayload()} payloadComplete={true} />
    ));

    for (const slug of SECTION_SLUGS) {
      expect(getSlotState(slug)).toBe("done");
    }
  });

  it("renders pending slots when both sections is empty and payload is null (no data yet)", () => {
    render(() => <Sidebar sections={{}} payload={null} />);

    for (const slug of SECTION_SLUGS) {
      expect(getSlotState(slug)).toBe("pending");
    }
  });

  it("prefers provided sections over payload-synthesis when sections has slots", () => {
    const sections = {
      safety__moderation: {
        state: "running",
        attempt_id: "a-1",
      },
    } as unknown as JobState["sections"];

    render(() => (
      <Sidebar sections={sections} payload={makePayload()} payloadComplete={true} />
    ));

    expect(getSlotState("safety__moderation")).toBe("running");
    // Other slots remain pending because they weren't in `sections`.
    expect(getSlotState("tone_dynamics__scd")).toBe("pending");
  });

  it("fills missing slots while analyzing before the server seeds section rows", () => {
    render(() => (
      <Sidebar
        sections={{}}
        payload={makePayload()}
        payloadComplete={false}
        jobStatus="analyzing"
      />
    ));

    expect(getSlotState("safety__moderation")).toBe("running");
    expect(getSlotState("tone_dynamics__scd")).toBe("running");
  });

  it("renders populated payload data for the new safety slots", () => {
    render(() => (
      <Sidebar
        sections={undefined}
        payloadComplete={true}
        payload={makePayload({
          web_risk: {
            findings: [
              {
                url: "https://phishing.example.test",
                threat_types: ["SOCIAL_ENGINEERING"],
              },
            ],
            urls_checked: 1,
          },
          image_moderation: {
            matches: [
              {
                utterance_id: "utt-image",
                image_url: "https://cdn.example.test/image.jpg",
                adult: 0.8,
                violence: 0,
                racy: 0,
                medical: 0,
                spoof: 0,
                flagged: true,
                max_likelihood: 0.8,
              },
            ],
          },
          video_moderation: {
            matches: [
              {
                utterance_id: "utt-video",
                video_url: "https://video.example.test/watch.mp4",
                flagged: true,
                max_likelihood: 1,
                segment_findings: [
                  {
                    start_offset_ms: 1000,
                    end_offset_ms: 1000,
                    adult: 0,
                    violence: 1,
                    racy: 0,
                    medical: 0,
                    spoof: 0,
                    flagged: true,
                    max_likelihood: 1,
                  },
                ],
              },
            ],
          },
        })}
      />
    ));

    expect(screen.getByTestId("report-safety__web_risk").textContent).toContain(
      "https://phishing.example.test",
    );
    expect(
      screen.getByTestId("report-safety__image_moderation").textContent,
    ).not.toContain("80%");
    expect(
      screen.getByTestId("report-safety__video_moderation").textContent,
    ).toContain("1.0s");
  });

  it("merges evidence and premises slots into the rendered claims report", () => {
    const sections = {
      facts_claims__dedup: {
        state: "done",
        attempt_id: "dedup-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "the project costs $5 million",
                category: "potentially_factual",
                occurrence_count: 2,
                author_count: 2,
                utterance_ids: ["u-1"],
                representative_authors: ["@a"],
              },
              {
                canonical_text: "this will make rents worse",
                category: "predictions",
                occurrence_count: 3,
                author_count: 2,
                utterance_ids: ["u-2"],
                representative_authors: ["@b"],
              },
            ],
            total_claims: 5,
            total_unique: 2,
          },
        },
      },
      facts_claims__evidence: {
        state: "done",
        attempt_id: "evidence-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "the project costs $5 million",
                category: "potentially_factual",
                occurrence_count: 2,
                author_count: 2,
                utterance_ids: ["u-1"],
                representative_authors: ["@a"],
                facts_to_verify: 0,
                supporting_facts: [
                  {
                    statement: "The project budget names a $5 million cost.",
                    source_kind: "utterance",
                    source_ref: "u-1",
                  },
                ],
              },
            ],
            total_claims: 5,
            total_unique: 2,
          },
        },
      },
      facts_claims__premises: {
        state: "done",
        attempt_id: "premises-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "this will make rents worse",
                category: "predictions",
                occurrence_count: 3,
                author_count: 2,
                utterance_ids: ["u-2"],
                representative_authors: ["@b"],
                premise_ids: ["premise-1"],
              },
            ],
            total_claims: 5,
            total_unique: 2,
            premises: {
              premises: {
                "premise-1": {
                  premise_id: "premise-1",
                  statement: "Supply would not increase quickly enough.",
                },
              },
            },
          },
        },
      },
      facts_claims__known_misinfo: {
        state: "done",
        attempt_id: "known-attempt",
        data: { known_misinformation: [] },
      },
    } as unknown as JobState["sections"];

    render(() => <Sidebar sections={sections} payload={makePayload()} />);

    expect(screen.getByTestId("deduped-claim-supporting-fact").textContent).toContain(
      "The project budget names a $5 million cost.",
    );
    expect(screen.getByTestId("deduped-claim-premise").textContent).toContain(
      "Supply would not increase quickly enough.",
    );
  });

  it("merges evidence facts-to-verify counts into the rendered claims report", () => {
    const sections = {
      facts_claims__dedup: {
        state: "done",
        attempt_id: "dedup-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "the project costs $5 million",
                category: "potentially_factual",
                occurrence_count: 2,
                author_count: 2,
                utterance_ids: ["u-1"],
                representative_authors: ["@a"],
                supporting_facts: [],
                facts_to_verify: 0,
              },
            ],
            total_claims: 2,
            total_unique: 1,
          },
        },
      },
      facts_claims__evidence: {
        state: "done",
        attempt_id: "evidence-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "the project costs $5 million",
                category: "potentially_factual",
                occurrence_count: 2,
                author_count: 2,
                utterance_ids: ["u-1"],
                representative_authors: ["@a"],
                supporting_facts: [],
                facts_to_verify: 2,
              },
            ],
            total_claims: 2,
            total_unique: 1,
          },
        },
      },
    } as unknown as JobState["sections"];

    render(() => <Sidebar sections={sections} payload={makePayload()} />);

    expect(screen.getByTestId("deduped-claim-facts-to-verify").textContent).toContain(
      "2 facts to verify",
    );
    expect(screen.queryByTestId("deduped-claim-no-sources")).toBeNull();
  });

  it("keeps evidence slots open with nonzero facts-to-verify counts", () => {
    const sections = {
      facts_claims__evidence: {
        state: "done",
        attempt_id: "evidence-attempt",
        data: {
          claims_report: {
            deduped_claims: [
              {
                canonical_text: "the project costs $5 million",
                category: "potentially_factual",
                occurrence_count: 2,
                author_count: 2,
                utterance_ids: ["u-1"],
                representative_authors: ["@a"],
                supporting_facts: [],
                facts_to_verify: 4,
              },
            ],
            total_claims: 2,
            total_unique: 1,
          },
        },
      },
    } as unknown as JobState["sections"];

    render(() => <Sidebar sections={sections} payload={makePayload()} />);

    expect(
      screen.getByTestId("slot-toggle-facts_claims__evidence").getAttribute("aria-expanded"),
    ).toBe("true");
    expect(screen.getByTestId("slot-count-facts_claims__evidence").textContent).toBe(
      "4 results",
    );
    expect(screen.getByTestId("report-facts_claims__evidence")).toBeDefined();
  });

  it("synthesizes evidence slot as failed when payload.evidence_status is 'failed' and suppresses 'No sources extracted'", () => {
    render(() => (
      <Sidebar
        sections={undefined}
        payloadComplete={true}
        payload={makePayload({
          facts_claims: {
            claims_report: {
              deduped_claims: [
                {
                  canonical_text: "the project costs $5 million",
                  category: "potentially_factual",
                  occurrence_count: 1,
                  author_count: 1,
                  utterance_ids: ["u-1"],
                  representative_authors: ["@a"],
                  supporting_facts: [],
                  premise_ids: [],
                  facts_to_verify: 0,
                },
              ],
              total_claims: 1,
              total_unique: 1,
            },
            known_misinformation: [],
            evidence_status: "failed",
            premises_status: "done",
          },
        })}
      />
    ));

    expect(getSlotState("facts_claims__evidence")).toBe("failed");
    expect(getSlotState("facts_claims__premises")).toBe("done");
    expect(screen.queryByTestId("deduped-claim-no-sources")).toBeNull();
  });

  it("falls back to 'done' synthesis when payload predates evidence_status (backward compat)", () => {
    render(() => (
      <Sidebar
        sections={undefined}
        payloadComplete={true}
        payload={makePayload()}
      />
    ));

    expect(getSlotState("facts_claims__evidence")).toBe("done");
    expect(getSlotState("facts_claims__premises")).toBe("done");
  });

  it("surfaces failed section names on partial jobs while keeping retry controls", () => {
    const sections = {
      safety__web_risk: {
        state: "failed",
        attempt_id: "failed-attempt",
        error: "Google Web Risk rejected URI mailto:hn@ycombinator.com",
      },
      safety__moderation: {
        state: "done",
        attempt_id: "done-attempt",
        data: { harmful_content_matches: [] },
      },
    } as unknown as JobState["sections"];

    render(() => (
      <Sidebar
        sections={sections}
        payload={makePayload()}
        jobStatus={"partial" as JobState["status"]}
        onRetry={() => undefined}
      />
    ));

    const banner = screen.getByTestId("partial-failure-banner");
    expect(banner.textContent).toContain("Web Risk");
    expect(screen.getByTestId("retry-safety__web_risk")).toBeDefined();
    expect(getSlotState("safety__moderation")).toBe("done");
  });
});
