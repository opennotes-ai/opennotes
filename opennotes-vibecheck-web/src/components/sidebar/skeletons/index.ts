import type { SectionSlug } from "~/lib/api-client.server";
import type { JSX } from "solid-js";
import SafetyModerationSkeleton from "./SafetyModerationSkeleton";
import FlashpointSkeleton from "./FlashpointSkeleton";
import ScdSkeleton from "./ScdSkeleton";
import ClaimsDedupSkeleton from "./ClaimsDedupSkeleton";
import KnownMisinfoSkeleton from "./KnownMisinfoSkeleton";
import SentimentSkeleton from "./SentimentSkeleton";
import SubjectiveSkeleton from "./SubjectiveSkeleton";

export {
  SafetyModerationSkeleton,
  FlashpointSkeleton,
  ScdSkeleton,
  ClaimsDedupSkeleton,
  KnownMisinfoSkeleton,
  SentimentSkeleton,
  SubjectiveSkeleton,
};

export const SKELETONS: Record<SectionSlug, () => JSX.Element> = {
  safety__moderation: SafetyModerationSkeleton,
  safety__web_risk: SafetyModerationSkeleton,
  safety__image_moderation: SafetyModerationSkeleton,
  safety__video_moderation: SafetyModerationSkeleton,
  tone_dynamics__flashpoint: FlashpointSkeleton,
  tone_dynamics__scd: ScdSkeleton,
  facts_claims__dedup: ClaimsDedupSkeleton,
  facts_claims__evidence: ClaimsDedupSkeleton,
  facts_claims__premises: ClaimsDedupSkeleton,
  facts_claims__known_misinfo: KnownMisinfoSkeleton,
  opinions_sentiments__sentiment: SentimentSkeleton,
  opinions_sentiments__subjective: SubjectiveSkeleton,
  opinions_sentiments__trends_oppositions: SentimentSkeleton,
};
