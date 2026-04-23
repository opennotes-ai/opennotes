import { createMemo, type JSX } from "solid-js";
import type {
  JobState,
  SectionSlot,
  SectionSlug,
  SidebarPayload,
} from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import SectionGroup, { type SlugToSlots } from "./SectionGroup";
import SafetySection from "./SafetySection";
import ToneDynamicsSection from "./ToneDynamicsSection";
import FactsClaimsSection from "./FactsClaimsSection";
import OpinionsSection from "./OpinionsSection";

type SafetyPayload = components["schemas"]["SafetySection"];
type ToneDynamicsPayload = components["schemas"]["ToneDynamicsSection"];
type FactsClaimsPayload = components["schemas"]["FactsClaimsSection"];
type OpinionsPayload = components["schemas"]["OpinionsSection"];
type SCDReport = components["schemas"]["SCDReport"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
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

function synthesizeSectionsFromPayload(
  payload: SidebarPayload,
): SlugToSlots {
  const attemptId = "payload";
  const flashpointData = {
    flashpoint_matches: payload.tone_dynamics.flashpoint_matches ?? [],
  };
  const scdData = payload.tone_dynamics.scd;
  const dedupData = {
    claims_report: payload.facts_claims.claims_report,
  };
  const knownMisinfoData = {
    known_misinformation: payload.facts_claims.known_misinformation ?? [],
  };
  const sentimentData = {
    sentiment_stats: payload.opinions_sentiments.opinions_report.sentiment_stats,
  };
  const subjectiveData = {
    subjective_claims:
      payload.opinions_sentiments.opinions_report.subjective_claims,
  };
  return {
    safety__moderation: doneSlot(attemptId, payload.safety),
    tone_dynamics__flashpoint: doneSlot(attemptId, flashpointData),
    tone_dynamics__scd: doneSlot(attemptId, scdData),
    facts_claims__dedup: doneSlot(attemptId, dedupData),
    facts_claims__known_misinfo: doneSlot(attemptId, knownMisinfoData),
    opinions_sentiments__sentiment: doneSlot(attemptId, sentimentData),
    opinions_sentiments__subjective: doneSlot(attemptId, subjectiveData),
  };
}

function asRecord(data: unknown): Record<string, unknown> {
  return (data ?? {}) as Record<string, unknown>;
}

function renderSafetyModeration(data: unknown): JSX.Element {
  const safety = (data ?? { harmful_content_matches: [] }) as SafetyPayload;
  return <SafetySection safety={safety} />;
}

function renderFlashpoint(data: unknown): JSX.Element {
  const matches = (asRecord(data).flashpoint_matches ?? []) as FlashpointMatch[];
  const toneDynamics: ToneDynamicsPayload = {
    scd: {
      summary: "",
      tone_labels: [],
      per_speaker_notes: {},
      insufficient_conversation: true,
    },
    flashpoint_matches: matches,
  };
  return <ToneDynamicsSection toneDynamics={toneDynamics} />;
}

function renderScd(data: unknown): JSX.Element {
  const scd = (data ?? {
    summary: "",
    tone_labels: [],
    per_speaker_notes: {},
    insufficient_conversation: true,
  }) as SCDReport;
  const toneDynamics: ToneDynamicsPayload = {
    scd,
    flashpoint_matches: [],
  };
  return <ToneDynamicsSection toneDynamics={toneDynamics} />;
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

function renderClaimsDedup(data: unknown): JSX.Element {
  const claimsReport = (asRecord(data).claims_report ?? EMPTY_CLAIMS_REPORT) as ClaimsReport;
  const factsClaims: FactsClaimsPayload = {
    claims_report: claimsReport,
    known_misinformation: [],
  };
  return <FactsClaimsSection factsClaims={factsClaims} />;
}

function renderKnownMisinfo(data: unknown): JSX.Element {
  const matches = (asRecord(data).known_misinformation ?? []) as FactCheckMatch[];
  const factsClaims: FactsClaimsPayload = {
    claims_report: EMPTY_CLAIMS_REPORT,
    known_misinformation: matches,
  };
  return <FactsClaimsSection factsClaims={factsClaims} />;
}

function renderSentiment(data: unknown): JSX.Element {
  const stats = (asRecord(data).sentiment_stats ?? EMPTY_SENTIMENT_STATS) as SentimentStats;
  const opinions: OpinionsPayload = {
    opinions_report: {
      sentiment_stats: stats,
      subjective_claims: [],
    },
  };
  return <OpinionsSection opinions={opinions} />;
}

function renderSubjective(data: unknown): JSX.Element {
  const claims = (asRecord(data).subjective_claims ?? []) as SubjectiveClaim[];
  const opinions: OpinionsPayload = {
    opinions_report: {
      sentiment_stats: EMPTY_SENTIMENT_STATS,
      subjective_claims: claims,
    },
  };
  return <OpinionsSection opinions={opinions} />;
}

const SAFETY_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  safety__moderation: renderSafetyModeration,
};

const TONE_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  tone_dynamics__flashpoint: renderFlashpoint,
  tone_dynamics__scd: renderScd,
};

const FACTS_RENDER: Partial<Record<SectionSlug, (data: unknown) => JSX.Element>> = {
  facts_claims__dedup: renderClaimsDedup,
  facts_claims__known_misinfo: renderKnownMisinfo,
};

const OPINIONS_RENDER: Partial<
  Record<SectionSlug, (data: unknown) => JSX.Element>
> = {
  opinions_sentiments__sentiment: renderSentiment,
  opinions_sentiments__subjective: renderSubjective,
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
