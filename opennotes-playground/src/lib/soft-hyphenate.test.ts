import { describe, expect, it } from "vitest";
import { softHyphenate } from "./soft-hyphenate";

describe("softHyphenate", () => {
  it("inserts soft hyphens at camelCase boundaries", () => {
    expect(softHyphenate("RaterDiversityScorer")).toBe("Rater\u00ADDiversity\u00ADScorer");
  });

  it("leaves all-caps unchanged", () => {
    expect(softHyphenate("MF")).toBe("MF");
  });

  it("leaves all-lowercase unchanged", () => {
    expect(softHyphenate("simple")).toBe("simple");
  });

  it("handles single word with leading capital", () => {
    expect(softHyphenate("Scorer")).toBe("Scorer");
  });

  it("handles empty string", () => {
    expect(softHyphenate("")).toBe("");
  });
});
