import type { SectionSlug } from "~/lib/api-client.server";

export const SECTION_DISPLAY_NAMES: Record<SectionSlug, string> = {
  safety__moderation: "Safety",
  tone_dynamics__flashpoint: "Flashpoint",
  tone_dynamics__scd: "SCD",
  facts_claims__dedup: "Claims",
  facts_claims__known_misinfo: "Known misinfo",
  opinions_sentiments__sentiment: "Sentiment",
  opinions_sentiments__subjective: "Subjective claims",
};

export function sectionDisplayName(slug: SectionSlug): string {
  return SECTION_DISPLAY_NAMES[slug];
}
