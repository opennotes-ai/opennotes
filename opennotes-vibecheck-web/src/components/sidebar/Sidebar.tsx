import { createMemo, type JSX } from "solid-js";
import type {
  JobState,
  SectionSlot,
  SectionSlug,
  SidebarPayload,
} from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import SectionGroup, { type SlugToSlots } from "./SectionGroup";
import {
  SafetyModerationReport,
  FlashpointReport,
  ScdReport,
  ClaimsDedupReport,
  KnownMisinfoReport,
  SentimentReport,
  SubjectiveReport,
} from "./reports";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
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
  onRetry?: (slug: SectionSlug) => void;
}

const SAFETY_SLUGS: SectionSlug[] = ["safety__moderation"];
const TONE_SLUGS: SectionSlug[] = [
  "tone_dynamics__flashpoint",
  "tone_dynamics__scd",
];
const FACTS_SLUGS: SectionSlug[] = [
  "facts_claims__dedup",
  "facts_claims__known_misinfo",
];
const OPINIONS_SLUGS: SectionSlug[] = [
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

const EMPTY_SCD: SCDReport = {
  summary: "",
  tone_labels: [],
  per_speaker_notes: {},
  insufficient_conversation: true,
};

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
  const flashpointData = {
    flashpoint_matches: payload.tone_dynamics?.flashpoint_matches ?? [],
  };
  const scdData = {
    scd: payload.tone_dynamics?.scd ?? EMPTY_SCD,
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

function extractFlashpointMatches(data: unknown): FlashpointMatch[] {
  return (asRecord(data).flashpoint_matches ?? []) as FlashpointMatch[];
}

function extractScd(data: unknown): SCDReport {
  return (asRecord(data).scd ?? EMPTY_SCD) as SCDReport;
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

const SAFETY_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  safety__moderation: (data) => (
    <SafetyModerationReport matches={extractHarmfulContentMatches(data)} />
  ),
};

const TONE_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  tone_dynamics__flashpoint: (data) => (
    <FlashpointReport matches={extractFlashpointMatches(data)} />
  ),
  tone_dynamics__scd: (data) => <ScdReport scd={extractScd(data)} />,
};

const FACTS_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  facts_claims__dedup: (data) => (
    <ClaimsDedupReport claimsReport={extractClaimsReport(data)} />
  ),
  facts_claims__known_misinfo: (data) => (
    <KnownMisinfoReport matches={extractKnownMisinfo(data)} />
  ),
};

const OPINIONS_RENDER: Partial<
  Record<SectionSlug, (data: unknown) => JSX.Element>
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
    if (props.sections) return props.sections as SlugToSlots;
    if (props.payload) return synthesizeSectionsFromPayload(props.payload);
    return {};
  });

  return (
    <aside
      aria-label="Analysis sidebar"
      aria-live="polite"
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
      />
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={effectiveSections()}
        render={TONE_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
      />
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={effectiveSections()}
        render={FACTS_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
      />
      <SectionGroup
        label="Opinions/sentiments"
        slugs={OPINIONS_SLUGS}
        sections={effectiveSections()}
        render={OPINIONS_RENDER}
        jobId={props.jobId}
        onRetry={props.onRetry}
      />
    </aside>
  );
}
