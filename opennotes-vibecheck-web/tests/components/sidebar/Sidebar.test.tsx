import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import Sidebar from "~/components/sidebar/Sidebar";
import type { JobState, SidebarPayload } from "~/lib/api-client.server";

afterEach(() => {
  cleanup();
});

const SECTION_SLUGS = [
  "safety__moderation",
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
  "facts_claims__dedup",
  "facts_claims__known_misinfo",
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
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
          neutral_pct: 0,
          mean_valence: 0,
        },
        subjective_claims: [],
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
    render(() => <Sidebar sections={undefined} payload={makePayload()} />);

    for (const slug of SECTION_SLUGS) {
      expect(getSlotState(slug)).toBe("done");
    }
  });

  it("renders all slots as done when sections is an empty object and payload is provided (real cache-hit backend shape)", () => {
    const emptySections = {} as unknown as JobState["sections"];

    render(() => <Sidebar sections={emptySections} payload={makePayload()} />);

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

    render(() => <Sidebar sections={sections} payload={makePayload()} />);

    expect(getSlotState("safety__moderation")).toBe("running");
    // Other slots remain pending because they weren't in `sections`.
    expect(getSlotState("tone_dynamics__scd")).toBe("pending");
  });
});
