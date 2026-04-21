import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@solidjs/testing-library";
import FactsClaimsSection from "../../../src/components/sidebar/FactsClaimsSection";
import type { components } from "../../../src/lib/generated-types";

type FactsClaims = components["schemas"]["FactsClaimsSection"];

afterEach(() => {
  cleanup();
});

describe("<FactsClaimsSection />", () => {
  it("orders deduped claims by occurrence_count descending", () => {
    const factsClaims: FactsClaims = {
      claims_report: {
        deduped_claims: [
          {
            canonical_text: "mild claim",
            occurrence_count: 2,
            author_count: 1,
            utterance_ids: ["u1"],
            representative_authors: ["alice"],
          },
          {
            canonical_text: "most repeated claim",
            occurrence_count: 30,
            author_count: 5,
            utterance_ids: ["u2", "u3"],
            representative_authors: ["bob", "carol"],
          },
          {
            canonical_text: "medium claim",
            occurrence_count: 8,
            author_count: 3,
            utterance_ids: ["u4"],
            representative_authors: ["dave"],
          },
        ],
        total_claims: 40,
        total_unique: 3,
      },
      known_misinformation: [],
    };

    render(() => <FactsClaimsSection factsClaims={factsClaims} />);

    const items = screen.getAllByTestId("deduped-claim-item");
    const texts = items.map((el) => el.textContent ?? "");
    expect(texts[0]).toMatch(/most repeated claim/);
    expect(texts[1]).toMatch(/medium claim/);
    expect(texts[2]).toMatch(/mild claim/);

    const occurrences = screen
      .getAllByTestId("deduped-claim-occurrences")
      .map((el) => el.textContent);
    expect(occurrences[0]).toMatch(/30/);
    expect(occurrences[1]).toMatch(/8/);
    expect(occurrences[2]).toMatch(/2/);
  });

  it("groups known misinformation by claim_text and renders reviews", () => {
    const factsClaims: FactsClaims = {
      claims_report: {
        deduped_claims: [],
        total_claims: 0,
        total_unique: 0,
      },
      known_misinformation: [
        {
          claim_text: "flat earth",
          publisher: "Snopes",
          review_title: "Is the earth flat?",
          review_url: "https://factcheck.example/a",
          textual_rating: "false",
          review_date: "2024-01-02",
        },
        {
          claim_text: "flat earth",
          publisher: "PolitiFact",
          review_title: "No, the earth is a sphere",
          review_url: "https://factcheck.example/b",
          textual_rating: "pants on fire",
          review_date: null,
        },
        {
          claim_text: "moon landing",
          publisher: "Reuters",
          review_title: "Moon landing was real",
          review_url: "https://factcheck.example/c",
          textual_rating: "true",
          review_date: null,
        },
      ],
    };

    render(() => <FactsClaimsSection factsClaims={factsClaims} />);

    // Two grouped items (flat earth, moon landing)
    const items = screen.getAllByTestId("known-misinfo-item");
    expect(items.length).toBe(2);
    expect(items[0].textContent).toMatch(/flat earth/);
    expect(items[0].textContent).toMatch(/Snopes/);
    expect(items[0].textContent).toMatch(/PolitiFact/);
    expect(items[1].textContent).toMatch(/moon landing/);

    const links = screen.getAllByRole("link", { name: /fact check/i });
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://factcheck.example/a",
      "https://factcheck.example/b",
      "https://factcheck.example/c",
    ]);
  });

  it("shows empty-state copy when both lists are empty", () => {
    render(() => (
      <FactsClaimsSection
        factsClaims={{
          claims_report: {
            deduped_claims: [],
            total_claims: 0,
            total_unique: 0,
          },
          known_misinformation: [],
        }}
      />
    ));

    expect(screen.getByText(/No repeated claims/)).not.toBeNull();
    expect(screen.getByText(/No known-misinformation matches/)).not.toBeNull();
  });
});
