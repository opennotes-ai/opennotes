import { describe, expect, it } from "vitest";
import { SITE_ORIGIN, siteUrl } from "./site-url";

describe("SITE_ORIGIN", () => {
  it("is the canonical vibecheck origin", () => {
    expect(SITE_ORIGIN).toBe("https://vibecheck.opennotes.ai");
  });
});

describe("siteUrl", () => {
  it("prepends SITE_ORIGIN to a leading-slash path", () => {
    expect(siteUrl("/api/og")).toBe("https://vibecheck.opennotes.ai/api/og");
  });

  it("prepends SITE_ORIGIN with a slash when path has no leading slash", () => {
    expect(siteUrl("api/og")).toBe("https://vibecheck.opennotes.ai/api/og");
  });

  it("handles root path", () => {
    expect(siteUrl("/")).toBe("https://vibecheck.opennotes.ai/");
  });

  it("preserves query strings", () => {
    expect(siteUrl("/api/og?job=123")).toBe(
      "https://vibecheck.opennotes.ai/api/og?job=123",
    );
  });

  it("returns an absolute URL starting with https://", () => {
    const result = siteUrl("/some/page");
    expect(result.startsWith("https://")).toBe(true);
  });
});
