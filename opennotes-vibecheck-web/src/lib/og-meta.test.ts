import { describe, expect, it } from "vitest";
import { deriveOgTitle, deriveOgDescription } from "./og-meta";

describe("deriveOgTitle", () => {
  it("returns pageTitle when present", () => {
    expect(deriveOgTitle({ pageTitle: "My Page", url: "https://example.com" })).toBe("My Page");
  });

  it("trims whitespace from pageTitle and treats whitespace-only as missing", () => {
    expect(deriveOgTitle({ pageTitle: "   ", url: "https://example.com" })).toBe("example.com");
  });

  it("returns hostname when pageTitle is missing but url is valid", () => {
    expect(deriveOgTitle({ pageTitle: null, url: "https://example.com/path" })).toBe("example.com");
  });

  it("returns vibecheck when both pageTitle and url are missing", () => {
    expect(deriveOgTitle({})).toBe("vibecheck");
  });

  it("returns vibecheck when url is malformed and pageTitle is missing", () => {
    expect(deriveOgTitle({ pageTitle: null, url: "not-a-url" })).toBe("vibecheck");
  });
});

describe("deriveOgDescription", () => {
  it("returns headline summary when present", () => {
    expect(
      deriveOgDescription({
        headlineSummary: "Breaking: Something happened today.",
        safetyRationale: "This content is safe.",
        url: "https://example.com",
      }),
    ).toBe("Breaking: Something happened today.");
  });

  it("falls back to safety rationale when headline summary is missing", () => {
    expect(
      deriveOgDescription({
        headlineSummary: null,
        safetyRationale: "Content appears safe.",
        url: "https://example.com",
      }),
    ).toBe("Content appears safe.");
  });

  it("falls back to Vibecheck for: <hostname> when both rationale fields are missing but url is valid", () => {
    expect(
      deriveOgDescription({
        headlineSummary: null,
        safetyRationale: null,
        url: "https://example.com/article",
      }),
    ).toBe("Vibecheck for: example.com");
  });

  it("returns generic tagline when all fields are missing", () => {
    expect(deriveOgDescription({})).toBe(
      "Analyze URLs and PDFs for tone, claims, safety, and opinions.",
    );
  });

  it("returns generic tagline when url is malformed and both text fields are missing", () => {
    expect(
      deriveOgDescription({ headlineSummary: null, safetyRationale: null, url: "not-a-url" }),
    ).toBe("Analyze URLs and PDFs for tone, claims, safety, and opinions.");
  });

  it("treats whitespace-only headline as missing and falls through to rationale", () => {
    expect(
      deriveOgDescription({
        headlineSummary: "   ",
        safetyRationale: "Content is safe.",
        url: "https://example.com",
      }),
    ).toBe("Content is safe.");
  });

  it("treats whitespace-only rationale as missing and falls through to url hostname", () => {
    expect(
      deriveOgDescription({
        headlineSummary: null,
        safetyRationale: "   ",
        url: "https://example.com",
      }),
    ).toBe("Vibecheck for: example.com");
  });
});
