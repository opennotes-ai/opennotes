"use server";

import { createHash, createHmac } from "node:crypto";

const WINDOW_MS = 60 * 60 * 1000;
const DEFAULT_LIMIT = 30;
const MAX_BUCKETS = 10_000;

interface Bucket {
  count: number;
  windowStart: number;
}

const buckets = new Map<string, Bucket>();

export type RateLimitOutcome = "allowed" | "denied" | "unattributable" | "disabled" | "shed";

export interface RateLimitDecision {
  allowed: boolean;
  retryAfterSec: number;
  ip: string | null;
  ipHashPrefix: string;
  outcome: RateLimitOutcome;
}

export function extractClientIp(headers: Headers): string | null {
  const xff = headers.get("x-forwarded-for");
  if (!xff) return null;
  const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  const raw = parts[parts.length - 2];
  if (!raw) return null;
  return normalizeIp(raw);
}

function normalizeIp(raw: string): string {
  let s = raw.toLowerCase();
  if (s.startsWith("[")) {
    const close = s.indexOf("]");
    if (close > 0) s = s.slice(1, close);
  } else if ((s.match(/:/g) ?? []).length === 1) {
    s = s.split(":", 1)[0] ?? s;
  }
  const pct = s.indexOf("%");
  if (pct > 0) s = s.slice(0, pct);
  return s;
}

function disableExplicit(): boolean {
  return process.env.VIBECHECK_RATE_LIMIT_DISABLED === "1";
}

function getLimit(): number {
  const raw = process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
  if (!raw) return DEFAULT_LIMIT;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_LIMIT;
}

function evictExpired(now: number): number {
  let removed = 0;
  for (const [k, b] of buckets) {
    if (now - b.windowStart >= WINDOW_MS) {
      buckets.delete(k);
      removed += 1;
    }
  }
  return removed;
}

function hashIp(ip: string | null): string {
  const subject = ip ?? "<no-ip>";
  const salt = process.env.VIBECHECK_LOG_HASH_SALT;
  if (salt) return createHmac("sha256", salt).update(subject).digest("hex").slice(0, 12);
  return createHash("sha256").update(subject).digest("hex").slice(0, 12);
}

export function checkAnalyzeRateLimit(
  headers: Headers,
  now: number = Date.now(),
): RateLimitDecision {
  const ip = extractClientIp(headers);
  const ipHashPrefix = hashIp(ip);
  if (disableExplicit()) {
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix, outcome: "disabled" };
  }
  if (ip === null) {
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix, outcome: "unattributable" };
  }
  const limit = getLimit();
  const bucket = buckets.get(ip);
  if (!bucket || now - bucket.windowStart >= WINDOW_MS) {
    if (buckets.size >= MAX_BUCKETS) {
      evictExpired(now);
      if (buckets.size >= MAX_BUCKETS) {
        return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix, outcome: "shed" };
      }
    }
    buckets.set(ip, { count: 1, windowStart: now });
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix, outcome: "allowed" };
  }
  if (bucket.count < limit) {
    bucket.count += 1;
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix, outcome: "allowed" };
  }
  const retryAfterSec = Math.max(
    1,
    Math.ceil((WINDOW_MS - (now - bucket.windowStart)) / 1000),
  );
  return { allowed: false, retryAfterSec, ip, ipHashPrefix, outcome: "denied" };
}

export function _resetRateLimitForTesting(): void {
  buckets.clear();
}
