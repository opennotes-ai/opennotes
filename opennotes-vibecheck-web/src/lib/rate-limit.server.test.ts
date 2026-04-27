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

  it("returns null for a single-entry XFF (no LB hop visible)", () => {
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

  it("strips port suffix from IPv4 host:port form (RFC 7239)", () => {
    const headers = new Headers({ "x-forwarded-for": "203.0.113.10:54321, 35.191.0.5" });
    expect(extractClientIp(headers)).toBe("203.0.113.10");
  });

  it("strips brackets and port suffix from [IPv6]:port form", () => {
    const headers = new Headers({
      "x-forwarded-for": "[2001:db8::1]:54321, 35.191.0.5",
    });
    expect(extractClientIp(headers)).toBe("2001:db8::1");
  });

  it("lowercases IPv6 addresses so case variants share a bucket", () => {
    const headers = new Headers({
      "x-forwarded-for": "2001:DB8::1, 35.191.0.5",
    });
    expect(extractClientIp(headers)).toBe("2001:db8::1");
  });

  it("strips IPv6 zone identifiers (%eth0)", () => {
    const headers = new Headers({
      "x-forwarded-for": "fe80::1%eth0, 35.191.0.5",
    });
    expect(extractClientIp(headers)).toBe("fe80::1");
  });
});

describe("checkAnalyzeRateLimit (per-IP window)", () => {
  beforeEach(() => {
    _resetRateLimitForTesting();
    delete process.env.VIBECHECK_RATE_LIMIT_DISABLED;
    process.env.VIBECHECK_RATE_LIMIT_PER_HOUR = "10";
  });

  afterEach(() => {
    _resetRateLimitForTesting();
    delete process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
    delete process.env.VIBECHECK_RATE_LIMIT_DISABLED;
    delete process.env.VIBECHECK_LOG_HASH_SALT;
  });

  function xffHeaders(clientIp: string): Headers {
    return new Headers({ "x-forwarded-for": `${clientIp}, 10.0.0.1` });
  }

  it("allows the first 10 requests from one client IP and denies the 11th", () => {
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 10; i++) {
      const decision = checkAnalyzeRateLimit(headers);
      expect(decision.allowed, `request ${i + 1}/11 should be allowed`).toBe(true);
      expect(decision.outcome).toBe("allowed");
    }
    const eleventh = checkAnalyzeRateLimit(headers);
    expect(eleventh.allowed).toBe(false);
    expect(eleventh.outcome).toBe("denied");
    expect(eleventh.retryAfterSec).toBeGreaterThan(0);
  });

  it("does not throttle a second client IP after the first is exhausted", () => {
    const headersA = xffHeaders("203.0.113.10");
    const headersB = xffHeaders("198.51.100.20");
    for (let i = 0; i < 10; i++) checkAnalyzeRateLimit(headersA);
    expect(checkAnalyzeRateLimit(headersA).allowed).toBe(false);
    expect(checkAnalyzeRateLimit(headersB).allowed).toBe(true);
  });

  it("limiter is enabled by default in non-production environments (no NODE_ENV gating)", () => {
    process.env.NODE_ENV = "test";
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 10; i++) {
      expect(checkAnalyzeRateLimit(headers).allowed).toBe(true);
    }
    expect(checkAnalyzeRateLimit(headers).allowed).toBe(false);
  });

  it("VIBECHECK_RATE_LIMIT_DISABLED=1 is the only way to disable the limiter", () => {
    process.env.VIBECHECK_RATE_LIMIT_DISABLED = "1";
    const headers = xffHeaders("203.0.113.10");
    for (let i = 0; i < 50; i++) {
      const decision = checkAnalyzeRateLimit(headers);
      expect(decision.allowed).toBe(true);
      expect(decision.outcome).toBe("disabled");
    }
  });

  it("unattributable requests (missing or single-entry XFF) are NOT coalesced into a shared bucket", () => {
    const noXff = new Headers();
    const singleEntry = new Headers({ "x-forwarded-for": "203.0.113.10" });
    for (let i = 0; i < 50; i++) {
      const a = checkAnalyzeRateLimit(noXff);
      const b = checkAnalyzeRateLimit(singleEntry);
      expect(a.allowed, `noXff request ${i + 1} should pass-through`).toBe(true);
      expect(a.outcome).toBe("unattributable");
      expect(b.outcome).toBe("unattributable");
    }
  });

  it("resets the bucket once the window elapses", () => {
    const headers = xffHeaders("203.0.113.10");
    const start = 1_700_000_000_000;
    for (let i = 0; i < 10; i++) checkAnalyzeRateLimit(headers, start);
    expect(checkAnalyzeRateLimit(headers, start).allowed).toBe(false);
    const after = start + 60 * 60 * 1000 + 1;
    expect(checkAnalyzeRateLimit(headers, after).allowed).toBe(true);
  });

  it("emits a deterministic 12-hex log identifier (HMAC when salt is set)", () => {
    process.env.VIBECHECK_LOG_HASH_SALT = "secret-salt";
    const headers = xffHeaders("203.0.113.10");
    const a = checkAnalyzeRateLimit(headers);
    expect(a.ipHashPrefix).toMatch(/^[0-9a-f]{12}$/);
    expect(a.ipHashPrefix).not.toContain("203.0.113.10");
    delete process.env.VIBECHECK_LOG_HASH_SALT;
    process.env.VIBECHECK_LOG_HASH_SALT = "different-salt";
    _resetRateLimitForTesting();
    const b = checkAnalyzeRateLimit(headers);
    expect(b.ipHashPrefix).not.toBe(a.ipHashPrefix);
  });

  it("MAX_BUCKETS overflow sheds new arrivals (allowed but with outcome=shed)", () => {
    process.env.VIBECHECK_RATE_LIMIT_PER_HOUR = "10";
    const start = 1_700_000_000_000;
    for (let i = 0; i < 10_000; i++) {
      const ip = `203.0.${(i >> 8) & 0xff}.${i & 0xff}`;
      checkAnalyzeRateLimit(xffHeaders(ip), start);
    }
    const overflow = checkAnalyzeRateLimit(xffHeaders("198.51.100.99"), start);
    expect(overflow.allowed).toBe(true);
    expect(overflow.outcome).toBe("shed");
  });
});
