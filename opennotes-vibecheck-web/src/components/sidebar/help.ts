import type { SectionSlugLiteral } from "~/lib/section-slots";

export interface SidebarHelpCopy {
  looksFor: string;
  means: string;
}

const SECTION_HELP: Record<string, SidebarHelpCopy> = {
  Safety: {
    looksFor: "Harmful content, risky links, and media safety signals.",
    means: "These results highlight material that may need moderation or extra review.",
  },
  "Tone/dynamics": {
    looksFor: "Conversation heat, speaker dynamics, and signs of derailment.",
    means: "These results explain how the exchange is developing, not whether it is true.",
  },
  "Facts/claims": {
    looksFor: "Repeated claims, deduped claim clusters, and known misinformation matches.",
    means: "These results show what factual assertions may need evidence or context.",
  },
  "Opinions/sentiments": {
    looksFor: "Sentiment balance and subjective claims that rely on personal judgment.",
    means: "These results separate tone and opinion from verifiable factual claims.",
  },
};

const SLOT_HELP: Record<SectionSlugLiteral, SidebarHelpCopy> = {
  safety__moderation: {
    looksFor: "Text that crosses content-safety moderation thresholds.",
    means: "Flagged items are the clearest safety concerns in the discussion text.",
  },
  safety__web_risk: {
    looksFor: "URLs associated with malware, social engineering, or other web threats.",
    means: "Findings suggest the linked page may be unsafe to open or share.",
  },
  safety__image_moderation: {
    looksFor: "Images whose SafeSearch categories cross the review threshold.",
    means: "Clear images were checked; flagged images should get moderator attention.",
  },
  safety__video_moderation: {
    looksFor: "Sampled video frames whose SafeSearch categories cross the review threshold.",
    means: "Flagged frames identify video moments that may need closer inspection.",
  },
  tone_dynamics__flashpoint: {
    looksFor: "Moments where the conversation may become heated or derail.",
    means: "Higher-risk flashpoints point to exchanges that may benefit from intervention.",
  },
  tone_dynamics__scd: {
    looksFor: "Speaker-level patterns in stance, framing, and conversational role.",
    means: "The summary explains how participants are interacting, not who is correct.",
  },
  facts_claims__dedup: {
    looksFor: "Similar factual claims repeated across the discussion.",
    means: "Grouped claims help reviewers evaluate one representative statement at a time.",
  },
  facts_claims__known_misinfo: {
    looksFor: "Claims that resemble entries from known fact-check databases.",
    means: "Matches are leads for review and should be checked against the cited source.",
  },
  opinions_sentiments__sentiment: {
    looksFor: "Positive, negative, and neutral language across utterances.",
    means: "Sentiment gives a temperature check on the discussion's emotional tone.",
  },
  opinions_sentiments__subjective: {
    looksFor: "Claims framed as judgments, preferences, or personal impressions.",
    means: "Subjective claims may need different handling than factual assertions.",
  },
};

export function sectionHelp(label: string): SidebarHelpCopy | null {
  return SECTION_HELP[label] ?? null;
}

export function slotHelp(slug: SectionSlugLiteral): SidebarHelpCopy {
  return SLOT_HELP[slug];
}
