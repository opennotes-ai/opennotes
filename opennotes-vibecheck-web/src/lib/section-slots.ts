import type { JobState, SectionSlot, SectionSlug } from "./api-client.server";

export const SECTION_SLUGS = [
  "safety__moderation",
  "safety__web_risk",
  "safety__image_moderation",
  "safety__video_moderation",
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
  "facts_claims__dedup",
  "facts_claims__evidence",
  "facts_claims__premises",
  "facts_claims__known_misinfo",
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
  "opinions_sentiments__trends_oppositions",
  "opinions_sentiments__highlights",
] as const satisfies readonly SectionSlug[];

export type SectionSlugLiteral = (typeof SECTION_SLUGS)[number];

export type StrictSectionSlots = Record<SectionSlugLiteral, SectionSlot>;

export type PartialSectionSlots = Partial<StrictSectionSlots>;

export function isSectionSlug(value: unknown): value is SectionSlugLiteral {
  return (
    typeof value === "string" &&
    (SECTION_SLUGS as readonly string[]).includes(value)
  );
}

export function getSection(
  state: JobState | null | undefined,
  slug: SectionSlugLiteral,
): SectionSlot | undefined {
  const sections = state?.sections;
  if (!sections) return undefined;
  return (sections as Partial<Record<string, SectionSlot>>)[slug];
}

export function asStrictSectionSlots(
  sections: JobState["sections"] | null | undefined,
): PartialSectionSlots {
  if (!sections) return {};
  const out: PartialSectionSlots = {};
  for (const slug of SECTION_SLUGS) {
    const slot = (sections as Partial<Record<string, SectionSlot>>)[slug];
    if (slot) out[slug] = slot;
  }
  return out;
}
