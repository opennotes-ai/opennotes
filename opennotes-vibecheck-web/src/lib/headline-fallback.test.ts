import { describe, expect, it } from "vitest";
import {
  buildHeadlineFallback,
  resolveHeadline,
} from "./headline-fallback";
import type { components } from "./generated-types";

type HeadlineSummary = components["schemas"]["HeadlineSummary"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];

const recommendation = (
  level: SafetyRecommendation["level"],
): SafetyRecommendation => ({
  level,
  rationale: "_",
  top_signals: [],
  unavailable_inputs: [],
});

describe("buildHeadlineFallback", () => {
  it("uses domain (sans www) and pageTitle joined with an em-dash when both are present", () => {
    const result = buildHeadlineFallback({
      url: "https://www.nypost.com/2026/04/27/news/some-article",
      pageTitle: "Headline of the Article",
      recommendation: null,
    });
    expect(result.text).toBe("nypost.com — Headline of the Article");
    expect(result.kind).toBe("stock");
    expect(result.source).toBe("fallback");
  });

  it("falls back to the cleaned URL last path segment when pageTitle is null", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/news/2026/04/some-article-title-here",
      pageTitle: null,
      recommendation: null,
    });
    expect(result.text).toBe("example.com — some article title here");
  });

  it("falls back to hostname when there is no usable path", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/",
      pageTitle: null,
      recommendation: null,
    });
    expect(result.text).toBe("example.com — example.com");
  });

  it("treats whitespace-only pageTitle as empty and walks the fallback chain", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/news/breaking",
      pageTitle: "   ",
      recommendation: null,
    });
    expect(result.text).toBe("example.com — breaking");
  });

  it("decodes URL path segments and normalizes underscores/dashes to spaces", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/articles/some_article-title%20here",
      pageTitle: null,
      recommendation: null,
    });
    expect(result.text).toBe("example.com — some article title here");
  });

  it("appends a safety verb only when recommendation is non-null", () => {
    const safe = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "Title",
      recommendation: recommendation("safe"),
    });
    expect(safe.text).toBe("example.com — Title — appears clean");

    const caution = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "Title",
      recommendation: recommendation("caution"),
    });
    expect(caution.text).toBe("example.com — Title — warrants caution");

    const unsafe = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "Title",
      recommendation: recommendation("unsafe"),
    });
    expect(unsafe.text).toBe("example.com — Title — appears unsafe");
  });

  it("omits the safety verb entirely when recommendation is null", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "Title",
      recommendation: null,
    });
    expect(result.text).toBe("example.com — Title");
  });

  it("returns hostname twice when the URL is malformed (graceful fallback, no throw)", () => {
    const result = buildHeadlineFallback({
      url: "not a url",
      pageTitle: null,
      recommendation: null,
    });
    expect(result.text.length).toBeGreaterThan(0);
    expect(result.kind).toBe("stock");
  });
});

describe("resolveHeadline", () => {
  it("returns the existing headline when payloadHeadline has non-empty text", () => {
    const real: HeadlineSummary = {
      text: "Real synthesized headline.",
      kind: "synthesized",
    };
    const result = resolveHeadline(real, {
      url: "https://example.com/x",
      pageTitle: "fallback title",
      recommendation: null,
    });
    expect(result.text).toBe(real.text);
    expect(result.kind).toBe(real.kind);
    expect(result.source).toBe("server");
  });

  it("returns the fallback when payloadHeadline is null", () => {
    const result = resolveHeadline(null, {
      url: "https://example.com/article",
      pageTitle: "Fallback Title",
      recommendation: null,
    });
    expect(result.text).toBe("example.com — Fallback Title");
    expect(result.kind).toBe("stock");
    expect(result.source).toBe("fallback");
  });

  it("returns the fallback when payloadHeadline is undefined", () => {
    const result = resolveHeadline(undefined, {
      url: "https://example.com/article",
      pageTitle: "Fallback Title",
      recommendation: null,
    });
    expect(result.text).toBe("example.com — Fallback Title");
  });

  it("returns the fallback when payloadHeadline.text is empty/whitespace", () => {
    const result = resolveHeadline(
      { text: "   ", kind: "synthesized" },
      {
        url: "https://example.com/article",
        pageTitle: "Fallback",
        recommendation: null,
      },
    );
    expect(result.text).toBe("example.com — Fallback");
  });
});
