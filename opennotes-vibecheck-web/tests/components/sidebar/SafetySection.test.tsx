import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import SafetySection from "../../../src/components/sidebar/SafetySection";
import type { components } from "../../../src/lib/generated-types";

type SafetyPayload = components["schemas"]["SafetySection"];

afterEach(() => {
  cleanup();
});

describe("<SafetySection />", () => {
  it("renders each match with its flagged categories and max score", () => {
    const safety: SafetyPayload = {
      harmful_content_matches: [
        {
          utterance_id: "u1",
          max_score: 0.82,
          categories: { harassment: true, hate: false },
          scores: { harassment: 0.82, hate: 0.1 },
          flagged_categories: ["harassment"],
        },
        {
          utterance_id: "u2",
          max_score: 0.91,
          categories: { hate: true, harassment: false },
          scores: { hate: 0.91, harassment: 0.3 },
          flagged_categories: ["hate", "violence"],
        },
      ],
    };

    render(() => <SafetySection safety={safety} />);

    const count = screen.getByTestId("safety-count");
    expect(count.textContent).toMatch(/2 flagged/);

    const categories = screen
      .getAllByTestId("safety-category")
      .map((el) => el.textContent);
    expect(categories).toEqual(["harassment", "hate", "violence"]);

    const scores = screen
      .getAllByTestId("safety-max-score")
      .map((el) => el.textContent);
    expect(scores).toEqual(["82%", "91%"]);
  });

  it("shows an empty state when there are no matches", () => {
    render(() => (
      <SafetySection safety={{ harmful_content_matches: [] }} />
    ));

    const count = screen.getByTestId("safety-count");
    expect(count.textContent).toMatch(/0 flagged/);
    expect(screen.getByTestId("safety-empty")).not.toBeNull();
  });

  it("falls back to a generic 'flagged' badge when no categories are returned", () => {
    render(() => (
      <SafetySection
        safety={{
          harmful_content_matches: [
            {
              utterance_id: "u1",
              max_score: 0.55,
              categories: {},
              scores: {},
              flagged_categories: [],
            },
          ],
        }}
      />
    ));

    const categories = screen
      .getAllByTestId("safety-category")
      .map((el) => el.textContent);
    expect(categories).toEqual(["flagged"]);
  });
});
