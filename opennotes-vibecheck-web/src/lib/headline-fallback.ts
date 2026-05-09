import type { components } from "./generated-types";

type HeadlineSummary = components["schemas"]["HeadlineSummary"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type SafetyLevel = SafetyRecommendation["level"];

export type HeadlineSource = "server" | "fallback";

export type ResolvedHeadline =
  | (HeadlineSummary & {
      source: "server";
    })
  | (HeadlineSummary & {
      kind: "stock";
      source: "fallback";
    });

interface ParsedHeadlineUrl {
  domain: string;
  pathTitle: string | null;
}

type FallbackHeadline = Extract<ResolvedHeadline, { source: "fallback" }>;

const NEUTRAL_TOKEN = "link";
const TRAILING_EXTENSION_RE = /\.[A-Za-z0-9]{1,6}$/;
const CONTROL_CHAR_RE = /\p{Cc}/gu;
const FORMAT_CHAR_RE = /\p{Cf}/gu;
const WHITESPACE_RE = /\s+/g;

const SAFETY_VERB = {
  safe: "appears clean",
  mild: "has minor concerns",
  caution: "warrants caution",
  unsafe: "appears unsafe",
} satisfies Record<SafetyLevel, string>;

function isSafetyLevel(value: string): value is SafetyLevel {
  return value in SAFETY_VERB;
}

function cleanText(text: string): string {
  return text
    .replace(FORMAT_CHAR_RE, "")
    .replace(CONTROL_CHAR_RE, " ")
    .replace(WHITESPACE_RE, " ")
    .trim();
}

function normalizeHost(host: string): string {
  return host.toLowerCase().replace(/^(?:www\.)+/, "") || NEUTRAL_TOKEN;
}

function parseHeadlineUrl(rawUrl: string): ParsedHeadlineUrl {
  const raw = rawUrl.trim();
  if (!raw) return { domain: NEUTRAL_TOKEN, pathTitle: null };

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return { domain: NEUTRAL_TOKEN, pathTitle: null };
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return { domain: NEUTRAL_TOKEN, pathTitle: null };
  }

  return {
    domain: normalizeHost(parsed.hostname),
    pathTitle: titleFromUrl(parsed),
  };
}

function safetyVerbFor(
  recommendation: SafetyRecommendation | null,
): string | null {
  const level = recommendation?.level;
  if (!level || !isSafetyLevel(level)) return null;
  return SAFETY_VERB[level];
}

function joinHeadlineParts(domain: string, title: string): string {
  return `${domain || NEUTRAL_TOKEN} — ${title || NEUTRAL_TOKEN}`;
}

export interface HeadlineFallbackInput {
  url: string;
  pageTitle: string | null | undefined;
  recommendation: SafetyRecommendation | null;
}

function decodeSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

function cleanSegment(segment: string): string {
  const decoded = decodeSegment(segment);
  const withoutExtension = decoded.replace(TRAILING_EXTENSION_RE, "");
  return cleanText(withoutExtension.replace(/[-_]+/g, " "));
}

function titleFromUrl(url: URL): string | null {
  const segments = url.pathname.split("/").filter(Boolean);
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const cleaned = cleanSegment(segments[i]);
    if (cleaned) return cleaned;
  }
  return null;
}

export function buildHeadlineFallback(
  input: HeadlineFallbackInput,
): FallbackHeadline {
  const { domain, pathTitle } = parseHeadlineUrl(input.url);
  const pageTitle = cleanText(input.pageTitle ?? "");
  const title = pageTitle || pathTitle || domain || NEUTRAL_TOKEN;

  const safetyVerb = safetyVerbFor(input.recommendation);
  const text = safetyVerb
    ? `${joinHeadlineParts(domain, title)} — ${safetyVerb}`
    : joinHeadlineParts(domain, title);

  return { text: cleanText(text), kind: "stock", source: "fallback" };
}

export function resolveHeadline(
  payloadHeadline: HeadlineSummary | null | undefined,
  fallbackInput: HeadlineFallbackInput,
): ResolvedHeadline {
  if (payloadHeadline && cleanText(payloadHeadline.text).length > 0) {
    return {
      ...payloadHeadline,
      text: cleanText(payloadHeadline.text),
      source: "server",
    };
  }
  return buildHeadlineFallback(fallbackInput);
}
