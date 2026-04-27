"use server";

// IMPORTANT: bucket state is process-local. With Cloud Run scale-out
// (max_instances=10), an attacker can multiply the per-IP budget by the
// number of warm instances. This is a documented v1 limitation; promote
// to a shared backend (Redis/Memorystore) before relying on this as the
// stable abuse control. See follow-up TASK-1483.12.

import { createHash, createHmac } from "node:crypto";

const WINDOW_MS = 60 * 60 * 1000;
const DEFAULT_LIMIT = 30;
const DEFAULT_UNATTRIBUTABLE_LIMIT = 60;
const MAX_BUCKETS = 10_000;
const UNATTRIBUTABLE_KEY = "<unattributable>";

interface Bucket {
  count: number;
  windowStart: number;
}

const buckets = new Map<string, Bucket>();

export type RateLimitOutcome =
  | "allowed"
  | "denied"
  | "denied_unattributable"
  | "denied_capacity"
  | "disabled";

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

function getUnattributableLimit(): number {
  const raw = process.env.VIBECHECK_RATE_LIMIT_UNATTRIBUTABLE_PER_HOUR;
  if (!raw) return DEFAULT_UNATTRIBUTABLE_LIMIT;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) && n >= 0 ? n : DEFAULT_UNATTRIBUTABLE_LIMIT;
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

function consume(
  key: string,
  limit: number,
  now: number,
): { allowed: boolean; retryAfterSec: number; capacityFull: boolean } {
  const bucket = buckets.get(key);
  if (!bucket || now - bucket.windowStart >= WINDOW_MS) {
    if (buckets.size >= MAX_BUCKETS) {
      evictExpired(now);
      if (buckets.size >= MAX_BUCKETS && !buckets.has(key)) {
        // Fail-closed: cannot allocate a new bucket without losing
        // enforcement on existing ones. Better to deny one request than
        // let a unique-IP attacker fill the map and bypass the limiter
        // for every subsequent address.
        return { allowed: false, retryAfterSec: 60, capacityFull: true };
      }
    }
    buckets.set(key, { count: 1, windowStart: now });
    return { allowed: true, retryAfterSec: 0, capacityFull: false };
  }
  if (bucket.count < limit) {
    bucket.count += 1;
    return { allowed: true, retryAfterSec: 0, capacityFull: false };
  }
  const retryAfterSec = Math.max(
    1,
    Math.ceil((WINDOW_MS - (now - bucket.windowStart)) / 1000),
  );
  return { allowed: false, retryAfterSec, capacityFull: false };
}

export function checkAnalyzeRateLimit(
  headers: Headers,
  now: number = Date.now(),
): RateLimitDecision {
  const ip = extractClientIp(headers);
  const ipHashPrefix = hashIp(ip);
  if (disableExplicit()) {
    return {
      allowed: true,
      retryAfterSec: 0,
      ip,
      ipHashPrefix,
      outcome: "disabled",
    };
  }
  if (ip === null) {
    // All unattributable traffic shares one tight global bucket so a
    // header-stripping proxy or topology regression cannot bypass the
    // per-user limit by simply removing X-Forwarded-For.
    const unattributableLimit = getUnattributableLimit();
    const result = consume(UNATTRIBUTABLE_KEY, unattributableLimit, now);
    if (result.allowed) {
      return {
        allowed: true,
        retryAfterSec: 0,
        ip,
        ipHashPrefix,
        outcome: "allowed",
      };
    }
    return {
      allowed: false,
      retryAfterSec: result.retryAfterSec,
      ip,
      ipHashPrefix,
      outcome: result.capacityFull
        ? "denied_capacity"
        : "denied_unattributable",
    };
  }
  const result = consume(ip, getLimit(), now);
  if (result.allowed) {
    return {
      allowed: true,
      retryAfterSec: 0,
      ip,
      ipHashPrefix,
      outcome: "allowed",
    };
  }
  return {
    allowed: false,
    retryAfterSec: result.retryAfterSec,
    ip,
    ipHashPrefix,
    outcome: result.capacityFull ? "denied_capacity" : "denied",
  };
}

export function _resetRateLimitForTesting(): void {
  buckets.clear();
}
