import { describe, expect, it } from "vitest";
import { isBlockingHost } from "./blocking-hosts";

describe("isBlockingHost", () => {
  it("matches reddit and linkedin roots", () => {
    expect(isBlockingHost("https://reddit.com")).toEqual({
      match: true,
      host: "reddit.com",
      family: "reddit",
    });
    expect(isBlockingHost("https://linkedin.com")).toEqual({
      match: true,
      host: "linkedin.com",
      family: "linkedin",
    });
  });

  it("matches subdomains for known blocking hosts", () => {
    expect(isBlockingHost("https://www.reddit.com/r/programming")).toEqual({
      match: true,
      host: "www.reddit.com",
      family: "reddit",
    });
    expect(
      isBlockingHost("https://subdomain.news.linkedin.com/feed"),
    ).toEqual({
      match: true,
      host: "subdomain.news.linkedin.com",
      family: "linkedin",
    });
  });

  it("is case-insensitive and tolerates a single trailing dot on hostnames", () => {
    expect(
      isBlockingHost("HTTPS://www.Reddit.Com./r/askscience"),
    ).toEqual({
      match: true,
      host: "www.reddit.com",
      family: "reddit",
    });
  });

  it("does not match x.com and mobile.x.com", () => {
    expect(isBlockingHost("https://x.com")).toEqual({ match: false });
    expect(isBlockingHost("https://mobile.x.com")).toEqual({ match: false });
    expect(isBlockingHost("https://example.com")).toEqual({ match: false });
  });

  it("does not match host lookalikes", () => {
    expect(isBlockingHost("https://reddit.com.evil.example")).toEqual({
      match: false,
    });
    expect(isBlockingHost("https://notreddit.com")).toEqual({ match: false });
    expect(isBlockingHost("https://mylinkedin.com")).toEqual({ match: false });
  });

  it("returns false for non-http(s) URLs", () => {
    expect(isBlockingHost("ftp://reddit.com")).toEqual({ match: false });
    expect(isBlockingHost("mailto:test@reddit.com")).toEqual({ match: false });
    expect(isBlockingHost("ws://linkedin.com")).toEqual({ match: false });
  });

  it("returns false for malformed URLs", () => {
    expect(isBlockingHost("not a URL")).toEqual({ match: false });
    expect(isBlockingHost("https://")).toEqual({ match: false });
  });

  it("does not match userinfo-supplied host spoofing", () => {
    expect(isBlockingHost("https://reddit.com@evil.example/")).toEqual({
      match: false,
    });
  });

  it("accepts URL objects as input", () => {
    expect(
      isBlockingHost(new URL("https://www.linkedin.com/feed")),
    ).toEqual({
      match: true,
      host: "www.linkedin.com",
      family: "linkedin",
    });
  });
});
