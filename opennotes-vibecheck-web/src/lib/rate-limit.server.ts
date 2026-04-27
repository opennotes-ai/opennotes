"use server";

import { createHash } from "node:crypto";

const WINDOW_MS = 60 * 60 * 1000;
const DEFAULT_LIMIT = 30;
const MAX_BUCKETS = 10_000;

interface Bucket {
  count: number;
  windowStart: number;
}

const buckets = new Map<string, Bucket>();

export interface RateLimitDecision {
  allowed: boolean;
  retryAfterSec: number;
  ip: string;
  ipHashPrefix: string;
}

export function extractClientIp(headers: Headers): string | null {
  const xff = headers.get("x-forwarded-for");
  if (!xff) return null;
  const parts = xff.split(",").map((s) => s.trim()).filter(Boolean);
  if (parts.length < 2) return null;
  return parts[parts.length - 2] ?? null;
}

function isDisabled(): boolean {
  if (process.env.VIBECHECK_RATE_LIMIT_DISABLED === "1") return true;
  if (process.env.NODE_ENV !== "production") return true;
  return false;
}

function getLimit(): number {
  const raw = process.env.VIBECHECK_RATE_LIMIT_PER_HOUR;
  if (!raw) return DEFAULT_LIMIT;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_LIMIT;
}

function evictExpired(now: number): void {
  for (const [k, b] of buckets) {
    if (now - b.windowStart >= WINDOW_MS) buckets.delete(k);
  }
}

function hashIp(ip: string): string {
  return createHash("sha256").update(ip).digest("hex").slice(0, 12);
}

export function checkAnalyzeRateLimit(
  headers: Headers,
  now: number = Date.now(),
): RateLimitDecision {
  const ip = extractClientIp(headers) ?? "unknown";
  const ipHashPrefix = hashIp(ip);
  if (isDisabled()) {
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix };
  }
  const limit = getLimit();
  const bucket = buckets.get(ip);
  if (!bucket || now - bucket.windowStart >= WINDOW_MS) {
    if (buckets.size >= MAX_BUCKETS) evictExpired(now);
    buckets.set(ip, { count: 1, windowStart: now });
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix };
  }
  if (bucket.count < limit) {
    bucket.count += 1;
    return { allowed: true, retryAfterSec: 0, ip, ipHashPrefix };
  }
  const retryAfterSec = Math.max(
    1,
    Math.ceil((WINDOW_MS - (now - bucket.windowStart)) / 1000),
  );
  return { allowed: false, retryAfterSec, ip, ipHashPrefix };
}

export function _resetRateLimitForTesting(): void {
  buckets.clear();
}
