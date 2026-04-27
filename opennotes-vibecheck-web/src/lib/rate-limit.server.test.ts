import { describe, expect, it, beforeEach, afterEach } from "vitest";

import {
  extractClientIp,
  checkAnalyzeRateLimit,
  _resetRateLimitForTesting,
} from "./rate-limit.server";

describe("extractClientIp (X-Forwarded-For trust boundary)", () => {
  it("returns null when X-Forwarded-For is absent", () => {
    expect(extractClientIp(new Headers())).toBeNull();
  });

  it("uses the second-to-last entry when XFF has multiple comma-separated IPs", () => {
    const headers = new Headers({
      "x-forwarded-for": "203.0.113.10, 198.51.100.20, 10.0.0.1",
    });
    expect(extractClientIp(headers)).toBe("198.51.100.20");
  });

  it("uses the second-to-last entry when XFF has exactly client + load-balancer", () => {
    const headers = new Headers({
      "x-forwarded-for": "203.0.113.10, 35.191.0.5",
    });
    expect(extractClientIp(headers)).toBe("203.0.113.10");
  });

  it("does NOT trust a single-entry XFF as the client IP (no LB hop visible)", () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.10" });
    expect(extractClientIp(headers)).toBeNull();
  });

  it("trims whitespace around comma-separated entries", () => {
    const headers = new Headers({
      "x-forwarded-for": "  203.0.113.10  ,  198.51.100.20  ,  10.0.0.1  ",
    });
    expect(extractClientIp(headers)).toBe("198.51.100.20");
  });

  it("ignores empty entries between commas", () => {
    const headers = new Headers({
      "x-forwarded-for": ",203.0.113.10,,10.0.0.1,",
    });
    expect(extractClientIp(headers)).toBe("203.0.113.10");
  });

  it("handles IPv6 addresses correctly", () => {
    const headers = new Headers({
      "x-forwarded-for": "2001:db8::1, 2001:db8::ffff",
    });
    expect(extractClientIp(headers)).toBe("2001:db8::1");
  });
});

describe("checkAnalyzeRateLimit (per-IP window)", () => {
  beforeEach(() => {
    _resetRateLimitForTesting();
    process.env.NODE_ENV = "production";
    process.env.VIBECHECK_RATE_LIMIT_DISABLED = "0";
    process.env.VIBECHECK_RATE_LIMIT_PER_HOUR = "10";
  });

  afterEach(() => {
    _resetRateLimitForTesting();
    delete process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
    delete process.env.VIBECHECK_RATE_LIMIT_DISABLED;
  });

  function xffHeaders(clientIp: string): Headers {
    return new Headers({ "x-forwarded-for": `${clientIp}, 10.0.0.1` });
  }

  it("allows the first 10 requests from one client IP and denies the 11th", () => {
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 10; i++) {
      const decision = checkAnalyzeRateLimit(headers);
      expect(decision.allowed, `request ${i + 1}/11 should be allowed`).toBe(true);
    }
    const eleventh = checkAnalyzeRateLimit(headers);
    expect(eleventh.allowed).toBe(false);
    expect(eleventh.retryAfterSec).toBeGreaterThan(0);
  });

  it("does not throttle a second client IP after the first is exhausted", () => {
    const headersA = xffHeaders("203.0.113.10");
    const headersB = xffHeaders("198.51.100.20");
    for (let i = 0; i < 10; i++) checkAnalyzeRateLimit(headersA);
    expect(checkAnalyzeRateLimit(headersA).allowed).toBe(false);
    expect(checkAnalyzeRateLimit(headersB).allowed).toBe(true);
  });

  it("disabled when NODE_ENV is not production", () => {
    process.env.NODE_ENV = "development";
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 100; i++) {
      expect(checkAnalyzeRateLimit(headers).allowed).toBe(true);
    }
  });

  it("can be force-disabled via VIBECHECK_RATE_LIMIT_DISABLED=1 even in production", () => {
    process.env.VIBECHECK_RATE_LIMIT_DISABLED = "1";
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 50; i++) {
      expect(checkAnalyzeRateLimit(headers).allowed).toBe(true);
    }
  });

  it("falls back to a single shared 'unknown' bucket when XFF is missing", () => {
    const noXff = new Headers();
    for (let i = 0; i < 10; i++) {
      expect(checkAnalyzeRateLimit(noXff).allowed).toBe(true);
    }
    expect(checkAnalyzeRateLimit(noXff).allowed).toBe(false);
  });

  it("resets the bucket once the window elapses", () => {
    const headers = xffHeaders("203.0.113.10");
    const start = 1_700_000_000_000;
    for (let i = 0; i < 10; i++) checkAnalyzeRateLimit(headers, start);
    expect(checkAnalyzeRateLimit(headers, start).allowed).toBe(false);
    const after = start + 60 * 60 * 1000 + 1;
    expect(checkAnalyzeRateLimit(headers, after).allowed).toBe(true);
  });

  it("emits a hashed IP prefix on the decision so logs do not store raw IPs", () => {
    const headers = xffHeaders("203.0.113.10");
    const decision = checkAnalyzeRateLimit(headers);
    expect(decision.ipHashPrefix).toMatch(/^[0-9a-f]{8,}$/);
    expect(decision.ipHashPrefix).not.toContain("203.0.113.10");
  });
});
