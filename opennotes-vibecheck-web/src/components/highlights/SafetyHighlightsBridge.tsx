import type { components } from "~/lib/generated-types";
import { createEffect, createMemo } from "solid-js";
import { useHighlights } from "./HighlightsStoreProvider";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type Divergence = components["schemas"]["Divergence"];

const SOURCE_LABELS: Record<string, string> = {
  // Server emits display-ready labels; client accepts raw slugs as defense-in-depth / backward compatibility.
  web_risk: "Web Risk",
  "web risk": "Web Risk",
  text: "Text moderation",
  openai: "Text moderation",
  gcp: "Text moderation",
  "text moderation": "Text moderation",
  text_moderation: "Text moderation",
  "text_moderation/gcp": "Text moderation",
  "text_moderation/openai": "Text moderation",
  image: "Image moderation",
  "image moderation": "Image moderation",
  image_moderation: "Image moderation",
  video: "Video moderation",
  "video moderation": "Video moderation",
  video_moderation: "Video moderation",
  combined: "Combined signals",
  combined_signals: "Combined signals",
  "combined signals": "Combined signals",
};

const RAW_SCORE_RE = /\b\d+\.\d+\b/;
const RAW_ENUM_RE =
  /\b(?:VERY_LIKELY|LIKELY|POSSIBLE|UNLIKELY|VERY_UNLIKELY|POTENTIALLY_HARMFUL_APPLICATION|SOCIAL_ENGINEERING|UNWANTED_SOFTWARE|MALWARE)\b/;
const RAW_IDENTIFIER_RE =
  /(?:^|[\s,;:])(?:[a-z]+(?:_[a-z]+)+)(?:$|[\s,;:])/;
const RAW_PROVIDER_RE = /\b(?:openai|gcp)\b/i;
const RAW_MODERATION_CATEGORIES = [
  "violence",
  "violence/graphic",
  "sexual",
  "sexual/minors",
  "hate",
  "hate/threatening",
  "harassment",
  "harassment/threatening",
  "self-harm",
  "self-harm/intent",
  "self-harm/instructions",
  "illicit",
  "illicit/violent",
];

function rawCategoryForms(category: string): string[] {
  return [
    category,
    category.replaceAll("/", "_").replaceAll("-", "_"),
    category.replaceAll("/", " ").replaceAll("-", " "),
  ];
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function containsRawModerationCategory(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return RAW_MODERATION_CATEGORIES.some((category) =>
    rawCategoryForms(category).some((form) => {
      const pattern = new RegExp(
        `(^|[^a-z0-9_-])${escapeRegExp(form)}($|[^a-z0-9_-])`,
      );
      return pattern.test(normalized);
    }),
  );
}

function normalizePhrase(value: string, fallback: string): string {
  const trimmed = value.trim();
  if (
    !trimmed ||
    RAW_SCORE_RE.test(trimmed) ||
    RAW_ENUM_RE.test(trimmed) ||
    RAW_IDENTIFIER_RE.test(trimmed) ||
    RAW_PROVIDER_RE.test(trimmed) ||
    containsRawModerationCategory(trimmed)
  ) {
    return fallback;
  }
  return trimmed.replace(/\s+/g, " ");
}

function divergenceSourceLabel(source: string): string {
  const trimmed = source.trim();
  const mapped = SOURCE_LABELS[trimmed.toLowerCase()];
  if (mapped) {
    return mapped;
  }
  if (trimmed.includes("/")) {
    return "Safety signal";
  }
  return normalizePhrase(trimmed, "Safety signal");
}

function divergenceDetail(detail: string): string {
  return normalizePhrase(detail, "Signal context adjusted");
}

function stripLeadingDirection(reason: string): string {
  return reason.replace(/^\s*(?:escalated|discounted)\s*:?\s*/i, "");
}

function divergenceReason(divergence: Divergence): string {
  const fallback =
    divergence.direction === "escalated"
      ? "Signal context escalated"
      : "Signal context discounted";
  return normalizePhrase(stripLeadingDirection(divergence.reason), fallback);
}

function divergenceTitle(divergence: Divergence): string {
  const direction =
    divergence.direction === "escalated" ? "Escalated" : "Discounted";
  return `${direction}: ${divergenceReason(divergence)}`;
}

function divergenceSeverity(divergence: Divergence): "info" | "warn" {
  return divergence.direction === "escalated" ? "warn" : "info";
}

export function SafetyHighlightsBridge(props: {
  recommendation: SafetyRecommendation | null;
}): null {
  const highlights = useHighlights();

  const divergences = createMemo(
    () => props.recommendation?.divergences ?? null,
    undefined,
    { equals: (a, b) => JSON.stringify(a) === JSON.stringify(b) },
  );

  createEffect(() => {
    const currentDivergences = divergences() ?? [];
    const mapped = currentDivergences.map((divergence, idx) => ({
      id: `safety-divergence:${idx}`,
      source: "safety-divergence" as const,
      title: divergenceTitle(divergence),
      detail: `${divergenceSourceLabel(divergence.signal_source)}: ${divergenceDetail(
        divergence.signal_detail,
      )}`,
      severity: divergenceSeverity(divergence),
    }));
    highlights.replaceForSource("safety-divergence", mapped);
  });

  return null;
}
