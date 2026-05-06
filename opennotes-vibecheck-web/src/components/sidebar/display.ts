import type { SectionSlug } from "~/lib/api-client.server";

export const SECTION_DISPLAY_NAMES: Record<SectionSlug, string> = {
  safety__moderation: "Safety",
  safety__web_risk: "Web Risk",
  safety__image_moderation: "Image safety",
  safety__video_moderation: "Video safety",
  tone_dynamics__flashpoint: "Flashpoint",
  tone_dynamics__scd: "SCD",
  facts_claims__dedup: "Claims",
  facts_claims__evidence: "Claim evidence",
  facts_claims__premises: "Claim premises",
  facts_claims__known_misinfo: "Known misinfo",
  opinions_sentiments__sentiment: "Sentiment",
  opinions_sentiments__subjective: "Subjective claims",
  opinions_sentiments__trends_oppositions: "Trends/oppositions",
};

export function sectionDisplayName(slug: SectionSlug): string {
  return SECTION_DISPLAY_NAMES[slug];
}
