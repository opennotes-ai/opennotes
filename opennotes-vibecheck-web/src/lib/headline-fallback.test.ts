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
    expect(result.text).toBe("link — link");
    expect(result.kind).toBe("stock");
  });

  it("uses neutral link token for empty and non-http URL input", () => {
    expect(
      buildHeadlineFallback({
        url: "",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("link — link");
    expect(
      buildHeadlineFallback({
        url: "javascript:alert(1)",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("link — link");
  });

  it("normalizes mixed-case hosts and strips repeated www prefixes", () => {
    const result = buildHeadlineFallback({
      url: "https://WWW.www.Example.COM/news",
      pageTitle: null,
      recommendation: null,
    });
    expect(result.text).toBe("example.com — news");
  });

  it("supports IDN/punycode, IPv6, and query-only URLs without raw URL echo", () => {
    expect(
      buildHeadlineFallback({
        url: "https://xn--bcher-kva.example/path",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("xn--bcher-kva.example — path");
    expect(
      buildHeadlineFallback({
        url: "https://[2001:db8::1]/",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("[2001:db8::1] — [2001:db8::1]");
    expect(
      buildHeadlineFallback({
        url: "https://example.com/?q=topic",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("example.com — example.com");
  });

  it("cleans titles and path segments before deciding whether they are usable", () => {
    expect(
      buildHeadlineFallback({
        url: "https://example.com/story-name.html",
        pageTitle: "Headline\u200b\u0007   with\n\nextra\tspace",
        recommendation: null,
      }).text,
    ).toBe("example.com — Headline with extra space");
    expect(
      buildHeadlineFallback({
        url: "https://example.com/\u200b",
        pageTitle: "\u200b\u200c\u200d",
        recommendation: null,
      }).text,
    ).toBe("example.com — example.com");
    expect(
      buildHeadlineFallback({
        url: "https://example.com/news/story-title.html",
        pageTitle: null,
        recommendation: null,
      }).text,
    ).toBe("example.com — story title");
  });

  it("returns a neutral non-empty string when URL and title are unusable", () => {
    const result = buildHeadlineFallback({
      url: "",
      pageTitle: "\u200b",
      recommendation: null,
    });
    expect(result.text).toBe("link — link");
    expect(result.text).not.toBe(" — ");
  });

  it("preserves full fallback headline text and does not add ellipsis", () => {
    const title = `${"a".repeat(250)}\u200b\u0007`;
    const result = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: title,
      recommendation: null,
    });
    expect(result.text).toBe(`example.com — ${"a".repeat(250)}`);
    expect(result.text).not.toContain("…");
    expect(result.text).not.toContain("\u0007");
    expect(result.text).toContain("a".repeat(250));
  });

  it("preserves RTL title text while normalizing whitespace", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "שלום   עולם",
      recommendation: null,
    });
    expect(result.text).toBe("example.com — שלום עולם");
  });

  it("ignores unknown recommendation levels instead of appending undefined", () => {
    const result = buildHeadlineFallback({
      url: "https://example.com/article",
      pageTitle: "Title",
      recommendation: {
        ...recommendation("safe"),
        level: "unknown",
      } as unknown as SafetyRecommendation,
    });
    expect(result.text).toBe("example.com — Title");
  });

  it("is deterministic for the same input", () => {
    const input = {
      url: "https://WWW.example.com/path/to/story.html",
      pageTitle: "Title",
      recommendation: recommendation("caution"),
    };
    expect(buildHeadlineFallback(input)).toEqual(buildHeadlineFallback(input));
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

  it("preserves full cleaned server headline text without truncation", () => {
    const headlineText =
      `Server-generated summary with ${"b".repeat(260)}\u200b\u0007 and safety note`;
    const result = resolveHeadline(
      {
        text: headlineText,
        kind: "synthesized",
      },
      {
        url: "https://example.com/article",
        pageTitle: "Fallback Title",
        recommendation: null,
      },
    );

    expect(result.text).toBe(
      `Server-generated summary with ${"b".repeat(260)} and safety note`,
    );
    expect(result.text).not.toContain("\u200b");
    expect(result.text).not.toContain("\u0007");
    expect(result.source).toBe("server");
    expect(result.kind).toBe("synthesized");
    expect(result.text).not.toContain("…");
  });
});
