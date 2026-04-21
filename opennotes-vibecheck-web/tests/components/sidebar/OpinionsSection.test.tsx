import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import OpinionsSection from "../../../src/components/sidebar/OpinionsSection";
import type { components } from "../../../src/lib/generated-types";

type OpinionsPayload = components["schemas"]["OpinionsSection"];

afterEach(() => {
  cleanup();
});

describe("<OpinionsSection />", () => {
  it("renders sentiment distribution percentages and mean valence", () => {
    const opinions: OpinionsPayload = {
      opinions_report: {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 42,
          negative_pct: 31,
          neutral_pct: 27,
          mean_valence: 0.18,
        },
        subjective_claims: [],
      },
    };

    render(() => <OpinionsSection opinions={opinions} />);

    const positive = screen.getByTestId("sentiment-positive") as HTMLElement;
    const negative = screen.getByTestId("sentiment-negative") as HTMLElement;
    expect(positive.style.width).toBe("42%");
    expect(negative.style.width).toBe("31%");

    expect(screen.getByText(/\+ 42%/)).not.toBeNull();
    expect(screen.getByText(/- 31%/)).not.toBeNull();

    const valence = screen.getByTestId("sentiment-mean-valence");
    expect(valence.textContent).toMatch(/\+0\.18/);
  });

  it("renders subjective claims with stance labels when present", () => {
    const opinions: OpinionsPayload = {
      opinions_report: {
        sentiment_stats: {
          per_utterance: [],
          positive_pct: 0,
          negative_pct: 0,
          neutral_pct: 100,
          mean_valence: 0,
        },
        subjective_claims: [
          {
            claim_text: "this is the best meal",
            utterance_id: "u1",
            stance: "supports",
          },
          {
            claim_text: "that team is terrible",
            utterance_id: "u2",
            stance: "opposes",
          },
        ],
      },
    };

    render(() => <OpinionsSection opinions={opinions} />);

    expect(screen.getByText(/this is the best meal/)).not.toBeNull();
    expect(screen.getByText(/that team is terrible/)).not.toBeNull();
    expect(screen.getByText(/Subjective \(2\)/)).not.toBeNull();
    const stanceLabels = screen.getAllByTestId("subjective-claim");
    expect(stanceLabels[0].textContent?.toLowerCase()).toContain("supports");
    expect(stanceLabels[1].textContent?.toLowerCase()).toContain("opposes");
  });

  it("shows empty copy when no subjective claims are present", () => {
    const opinions: OpinionsPayload = {
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
    };

    render(() => <OpinionsSection opinions={opinions} />);
    expect(screen.getByText(/No subjective claims/)).not.toBeNull();
  });
});
