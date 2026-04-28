import type { components } from "./generated-types";

type HeadlineSummary = components["schemas"]["HeadlineSummary"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type SafetyLevel = SafetyRecommendation["level"];
type HeadlineSource = "server" | "fallback";

export type ResolvedHeadline = HeadlineSummary & {
  source: HeadlineSource;
};

export interface HeadlineFallbackInput {
  url: string;
  pageTitle: string | null | undefined;
  recommendation: SafetyRecommendation | null;
}

const SAFETY_VERB: Record<SafetyLevel, string> = {
  safe: "appears clean",
  caution: "warrants caution",
  unsafe: "appears unsafe",
};

function stripWww(host: string): string {
  return host.startsWith("www.") ? host.slice(4) : host;
}

function cleanSegment(segment: string): string {
  let decoded: string;
  try {
    decoded = decodeURIComponent(segment);
  } catch {
    decoded = segment;
  }
  return decoded.replace(/[-_]+/g, " ").trim();
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
): ResolvedHeadline {
  let domain = "";
  let pathTitle: string | null = null;
  try {
    const parsed = new URL(input.url);
    domain = stripWww(parsed.hostname);
    pathTitle = titleFromUrl(parsed);
  } catch {
    domain = input.url || "";
  }

  const trimmedPageTitle = (input.pageTitle ?? "").trim();
  const title = trimmedPageTitle || pathTitle || domain;

  let text = `${domain} — ${title}`;
  if (input.recommendation) {
    text = `${text} — ${SAFETY_VERB[input.recommendation.level]}`;
  }

  return { text, kind: "stock", source: "fallback" };
}

export function resolveHeadline(
  payloadHeadline: HeadlineSummary | null | undefined,
  fallbackInput: HeadlineFallbackInput,
): ResolvedHeadline {
  if (payloadHeadline && payloadHeadline.text.trim().length > 0) {
    return { ...payloadHeadline, source: "server" };
  }
  return buildHeadlineFallback(fallbackInput);
}
