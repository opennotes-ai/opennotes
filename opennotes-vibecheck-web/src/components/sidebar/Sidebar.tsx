import { createMemo, type JSX } from "solid-js";
import type {
  JobState,
  SectionSlot,
  SidebarPayload,
} from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import { makeEmptyScd } from "~/lib/sidebar-defaults";
import {
  asStrictSectionSlots,
  type SectionSlugLiteral,
} from "~/lib/section-slots";
import SectionGroup, { type SlugToSlots } from "./SectionGroup";
import {
  SafetyModerationReport,
  WebRiskReport,
  ImageModerationReport,
  VideoModerationReport,
  FlashpointReport,
  ScdReport,
  ClaimsDedupReport,
  KnownMisinfoReport,
  SentimentReport,
  SubjectiveReport,
} from "./reports";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type WebRiskFinding = components["schemas"]["WebRiskFinding"];
type ImageModerationMatch = components["schemas"]["ImageModerationMatch"];
type VideoModerationMatch = components["schemas"]["VideoModerationMatch"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type SCDReport = components["schemas"]["SCDReport"];
type FactCheckMatch = components["schemas"]["FactCheckMatch"];
type SentimentStats = components["schemas"]["SentimentStatsReport"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];
type ClaimsReport = components["schemas"]["ClaimsReport"];

export interface SidebarProps {
  sections?: JobState["sections"];
  payload?: SidebarPayload | null;
  jobId?: string;
  onRetry?: (slug: SectionSlugLiteral) => void;
  cachedHint?: boolean;
}

const SAFETY_SLUGS: SectionSlugLiteral[] = [
  "safety__moderation",
  "safety__web_risk",
  "safety__image_moderation",
  "safety__video_moderation",
];
const TONE_SLUGS: SectionSlugLiteral[] = [
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
];
const FACTS_SLUGS: SectionSlugLiteral[] = [
  "facts_claims__dedup",
  "facts_claims__known_misinfo",
];
const OPINIONS_SLUGS: SectionSlugLiteral[] = [
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
];

function doneSlot(attemptId: string, data: unknown): SectionSlot {
  return {
    state: "done",
    attempt_id: attemptId,
    data: data as SectionSlot["data"],
  };
}

const EMPTY_CLAIMS_REPORT: ClaimsReport = {
  deduped_claims: [],
  total_claims: 0,
  total_unique: 0,
};

const EMPTY_SENTIMENT_STATS: SentimentStats = {
  per_utterance: [],
  positive_pct: 0,
  negative_pct: 0,
  neutral_pct: 0,
  mean_valence: 0,
};

function synthesizeSectionsFromPayload(
  payload: SidebarPayload,
): SlugToSlots {
  const attemptId = "payload";
  const safetyData = {
    harmful_content_matches:
      payload.safety?.harmful_content_matches ?? [],
  };
  const webRiskData = {
    findings: payload.web_risk?.findings ?? [],
  };
  const imageModerationData = {
    matches: payload.image_moderation?.matches ?? [],
  };
  const videoModerationData = {
    matches: payload.video_moderation?.matches ?? [],
  };
  const flashpointData = {
    flashpoint_matches: payload.tone_dynamics?.flashpoint_matches ?? [],
  };
  const scdData = {
    scd: payload.tone_dynamics?.scd ?? makeEmptyScd(),
  };
  const claimsDedupData = {
    claims_report:
      payload.facts_claims?.claims_report ?? EMPTY_CLAIMS_REPORT,
  };
  const knownMisinfoData = {
    known_misinformation:
      payload.facts_claims?.known_misinformation ?? [],
  };
  const sentimentData = {
    sentiment_stats:
      payload.opinions_sentiments?.opinions_report?.sentiment_stats ??
      EMPTY_SENTIMENT_STATS,
  };
  const subjectiveData = {
    subjective_claims:
      payload.opinions_sentiments?.opinions_report?.subjective_claims ?? [],
  };
  return {
    safety__moderation: doneSlot(attemptId, safetyData),
    safety__web_risk: doneSlot(attemptId, webRiskData),
    safety__image_moderation: doneSlot(attemptId, imageModerationData),
    safety__video_moderation: doneSlot(attemptId, videoModerationData),
    tone_dynamics__flashpoint: doneSlot(attemptId, flashpointData),
    tone_dynamics__scd: doneSlot(attemptId, scdData),
    facts_claims__dedup: doneSlot(attemptId, claimsDedupData),
    facts_claims__known_misinfo: doneSlot(attemptId, knownMisinfoData),
    opinions_sentiments__sentiment: doneSlot(attemptId, sentimentData),
    opinions_sentiments__subjective: doneSlot(attemptId, subjectiveData),
  };
}

function asRecord(data: unknown): Record<string, unknown> {
  return (data ?? {}) as Record<string, unknown>;
}

function extractHarmfulContentMatches(data: unknown): HarmfulContentMatch[] {
  return (asRecord(data).harmful_content_matches ?? []) as HarmfulContentMatch[];
}

function extractWebRiskFindings(data: unknown): WebRiskFinding[] {
  return (asRecord(data).findings ?? []) as WebRiskFinding[];
}

function extractImageModerationMatches(data: unknown): ImageModerationMatch[] {
  return (asRecord(data).matches ?? []) as ImageModerationMatch[];
}

function extractVideoModerationMatches(data: unknown): VideoModerationMatch[] {
  return (asRecord(data).matches ?? []) as VideoModerationMatch[];
}

function extractFlashpointMatches(data: unknown): FlashpointMatch[] {
  return (asRecord(data).flashpoint_matches ?? []) as FlashpointMatch[];
}

function extractScd(data: unknown): SCDReport {
  return (asRecord(data).scd ?? makeEmptyScd()) as SCDReport;
}

function extractClaimsReport(data: unknown): ClaimsReport {
  return (asRecord(data).claims_report ?? EMPTY_CLAIMS_REPORT) as ClaimsReport;
}

function extractKnownMisinfo(data: unknown): FactCheckMatch[] {
  return (asRecord(data).known_misinformation ?? []) as FactCheckMatch[];
}

function extractSentimentStats(data: unknown): SentimentStats {
  return (asRecord(data).sentiment_stats ?? EMPTY_SENTIMENT_STATS) as SentimentStats;
}

function extractSubjectiveClaims(data: unknown): SubjectiveClaim[] {
  return (asRecord(data).subjective_claims ?? []) as SubjectiveClaim[];
}

const SAFETY_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  safety__moderation: (data) => (
    <SafetyModerationReport matches={extractHarmfulContentMatches(data)} />
  ),
  safety__web_risk: (data) => (
    <WebRiskReport findings={extractWebRiskFindings(data)} />
  ),
  safety__image_moderation: (data) => (
    <ImageModerationReport matches={extractImageModerationMatches(data)} />
  ),
  safety__video_moderation: (data) => (
    <VideoModerationReport matches={extractVideoModerationMatches(data)} />
  ),
};

const TONE_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  tone_dynamics__flashpoint: (data) => (
    <FlashpointReport matches={extractFlashpointMatches(data)} />
  ),
  tone_dynamics__scd: (data) => <ScdReport scd={extractScd(data)} />,
};

const FACTS_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  facts_claims__dedup: (data) => (
    <ClaimsDedupReport claimsReport={extractClaimsReport(data)} />
  ),
  facts_claims__known_misinfo: (data) => (
    <KnownMisinfoReport matches={extractKnownMisinfo(data)} />
  ),
};

const OPINIONS_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  opinions_sentiments__sentiment: (data) => (
    <SentimentReport stats={extractSentimentStats(data)} />
  ),
  opinions_sentiments__subjective: (data) => (
    <SubjectiveReport claims={extractSubjectiveClaims(data)} />
  ),
};

export default function Sidebar(props: SidebarProps) {
  const effectiveSections = createMemo<SlugToSlots>(() => {
    const raw = props.sections;
    const hasSlots = raw !== undefined && Object.keys(raw).length > 0;
    if (hasSlots) return asStrictSectionSlots(raw);
    if (props.payload) return synthesizeSectionsFromPayload(props.payload);
    return {};
  });

  return (
    <aside
      aria-label="Analysis sidebar"
      data-testid="analysis-sidebar"
      class="flex w-full flex-col gap-4"
    >
      <SectionGroup
        label="Safety"
        slugs={SAFETY_SLUGS}
        sections={effectiveSections()}
        render={SAFETY_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
      />
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={effectiveSections()}
        render={TONE_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
      />
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={effectiveSections()}
        render={FACTS_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
      />
      <SectionGroup
        label="Opinions/sentiments"
        slugs={OPINIONS_SLUGS}
        sections={effectiveSections()}
        render={OPINIONS_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
      />
    </aside>
  );
}
