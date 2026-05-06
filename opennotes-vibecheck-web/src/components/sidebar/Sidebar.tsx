import { Show, createMemo, type JSX } from "solid-js";
import type {
  JobState,
  JobStatus,
  SectionSlot,
  SidebarPayload,
} from "~/lib/api-client.server";
import type { components } from "~/lib/generated-types";
import { makeEmptyScd } from "~/lib/sidebar-defaults";
import {
  SECTION_SLUGS,
  asStrictSectionSlots,
  type SectionSlugLiteral,
} from "~/lib/section-slots";
import SectionGroup, {
  type SlugToSlots,
  type SlotCountBadge,
} from "./SectionGroup";
import ExtractingIndicator from "./ExtractingIndicator";
import { sectionDisplayName } from "./display";
import {
  SafetyModerationReport,
  SafetyRecommendationReport,
  WebRiskReport,
  ImageModerationReport,
  VideoModerationReport,
  FlashpointReport,
  ScdReport,
  ClaimsDedupReport,
  KnownMisinfoReport,
  SentimentReport,
  SubjectiveReport,
  TrendsOppositionsReport,
  EMPTY_TRENDS_OPPOSITIONS_REPORT,
} from "./reports";

type HarmfulContentMatch = components["schemas"]["HarmfulContentMatch"];
type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type WebRiskFinding = components["schemas"]["WebRiskFinding"];
type ImageModerationMatch = components["schemas"]["ImageModerationMatch"];
type VideoModerationMatch = components["schemas"]["VideoModerationMatch"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type SCDReport = components["schemas"]["SCDReport"];
type FactCheckMatch = components["schemas"]["FactCheckMatch"];
type SentimentStats = components["schemas"]["SentimentStatsReport"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];
type TrendsOppositionsReportData =
  components["schemas"]["TrendsOppositionsReport"];
type ClaimsReport = components["schemas"]["ClaimsReport"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

export interface SidebarProps {
  sections?: JobState["sections"];
  payload?: SidebarPayload | null;
  payloadComplete?: boolean;
  jobId?: string;
  jobStatus?: JobStatus;
  class?: string;
  onRetry?: (slug: SectionSlugLiteral) => void;
  cachedHint?: boolean;
  onUtteranceClick?: (id: string) => void;
  canJumpToUtterance?: boolean;
  activityLabel?: string | null;
  activityAt?: string | null;
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
  "facts_claims__evidence",
  "facts_claims__premises",
  "facts_claims__known_misinfo",
];
const OPINIONS_SLUGS: SectionSlugLiteral[] = [
  "opinions_sentiments__sentiment",
  "opinions_sentiments__subjective",
  "opinions_sentiments__trends_oppositions",
];

function doneSlot(attemptId: string, data: unknown): SectionSlot {
  return {
    state: "done",
    attempt_id: attemptId,
    data: data as SectionSlot["data"],
  };
}

type SlotState = SectionSlot["state"];

function statusSlot(
  attemptId: string,
  status: SlotState | undefined,
  data: unknown,
): SectionSlot {
  const state: SlotState = status ?? "done";
  return {
    state,
    attempt_id: attemptId,
    data: state === "done" ? (data as SectionSlot["data"]) : undefined,
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
    urls_checked: payload.web_risk?.urls_checked ?? 0,
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
  const claimsEvidenceData = {
    claims_report:
      payload.facts_claims?.claims_report ?? EMPTY_CLAIMS_REPORT,
  };
  const claimsPremisesData = {
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
  const evidenceStatus = payload.facts_claims?.evidence_status as
    | SlotState
    | undefined;
  const premisesStatus = payload.facts_claims?.premises_status as
    | SlotState
    | undefined;
  const trendsOppositionsData = {
    trends_oppositions_report:
      payload.opinions_sentiments?.trends_oppositions ??
      EMPTY_TRENDS_OPPOSITIONS_REPORT,
  };
  return {
    safety__moderation: doneSlot(attemptId, safetyData),
    safety__web_risk: doneSlot(attemptId, webRiskData),
    safety__image_moderation: doneSlot(attemptId, imageModerationData),
    safety__video_moderation: doneSlot(attemptId, videoModerationData),
    tone_dynamics__flashpoint: doneSlot(attemptId, flashpointData),
    tone_dynamics__scd: doneSlot(attemptId, scdData),
    facts_claims__dedup: doneSlot(attemptId, claimsDedupData),
    facts_claims__evidence: statusSlot(
      attemptId,
      evidenceStatus,
      claimsEvidenceData,
    ),
    facts_claims__premises: statusSlot(
      attemptId,
      premisesStatus,
      claimsPremisesData,
    ),
    facts_claims__known_misinfo: doneSlot(attemptId, knownMisinfoData),
    opinions_sentiments__sentiment: doneSlot(attemptId, sentimentData),
    opinions_sentiments__subjective: doneSlot(attemptId, subjectiveData),
    opinions_sentiments__trends_oppositions: doneSlot(
      attemptId,
      trendsOppositionsData,
    ),
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

function extractWebRiskUrlsChecked(data: unknown): number {
  const raw = asRecord(data).urls_checked;
  return typeof raw === "number" ? raw : 0;
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

function mergeClaimsReportEnrichments(
  base: ClaimsReport,
  evidence: ClaimsReport,
  premises: ClaimsReport,
): ClaimsReport {
  const evidenceByText = new Map(
    (evidence.deduped_claims ?? []).map((claim) => [
      claim.canonical_text,
      claim,
    ]),
  );
  const premisesByText = new Map(
    (premises.deduped_claims ?? []).map((claim) => [
      claim.canonical_text,
      claim,
    ]),
  );
  return {
    ...base,
    deduped_claims: (base.deduped_claims ?? []).map((claim) => ({
      ...claim,
      supporting_facts:
        evidenceByText.get(claim.canonical_text)?.supporting_facts ??
        claim.supporting_facts ??
        [],
      premise_ids:
        premisesByText.get(claim.canonical_text)?.premise_ids ??
        claim.premise_ids ??
        [],
    })),
    premises: premises.premises ?? base.premises,
  };
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
function extractTrendsOppositionsReport(
  data: unknown,
): TrendsOppositionsReportData {
  return (asRecord(data).trends_oppositions_report ??
    EMPTY_TRENDS_OPPOSITIONS_REPORT) as TrendsOppositionsReportData;
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

const SAFETY_EMPTINESS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => boolean>
> = {
  safety__moderation: (data) => extractHarmfulContentMatches(data).length === 0,
  safety__web_risk: (data) => extractWebRiskFindings(data).length === 0,
  safety__image_moderation: (data) => {
    const matches = extractImageModerationMatches(data);
    return matches.length === 0 || matches.every((match) => !match.flagged);
  },
  safety__video_moderation: (data) =>
    extractVideoModerationMatches(data).length === 0,
};

const SAFETY_COUNTS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => SlotCountBadge>
> = {
  safety__moderation: (data) => {
    const total = extractHarmfulContentMatches(data).length;
    return { total };
  },
  safety__web_risk: (data) => {
    const flagged = extractWebRiskFindings(data).length;
    const total = extractWebRiskUrlsChecked(data);
    return { flagged, total, kind: "flagged" };
  },
  safety__image_moderation: (data) => {
    const matches = extractImageModerationMatches(data);
    return {
      flagged: matches.filter((match) => match.flagged).length,
      total: matches.length,
      kind: "flagged",
    };
  },
  safety__video_moderation: (data) => {
    const matches = extractVideoModerationMatches(data);
    return {
      flagged: matches.filter((match) => match.flagged).length,
      total: matches.length,
      kind: "flagged",
    };
  },
};

const TONE_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  tone_dynamics__flashpoint: (data) => (
    <FlashpointReport matches={extractFlashpointMatches(data)} />
  ),
  tone_dynamics__scd: (data) => <ScdReport scd={extractScd(data)} />,
};

const TONE_EMPTINESS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => boolean>
> = {
  tone_dynamics__flashpoint: (data) => extractFlashpointMatches(data).length === 0,
  tone_dynamics__scd: (data) => {
    const scd = extractScd(data);
    return (
      scd.insufficient_conversation &&
      (scd.tone_labels ?? []).length === 0 &&
      Object.keys(scd.per_speaker_notes ?? {}).length === 0
    );
  },
};

const TONE_COUNTS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => SlotCountBadge>
> = {
  tone_dynamics__flashpoint: (data) => {
    const total = extractFlashpointMatches(data).length;
    return { total };
  },
  tone_dynamics__scd: (data) => {
    const scd = extractScd(data);
    const total =
      (scd.tone_labels ?? []).length +
      Object.keys(scd.per_speaker_notes ?? {}).length;
    return { total };
  },
};

const FACTS_RENDER: Partial<
  Record<SectionSlugLiteral, (data: unknown) => JSX.Element>
> = {
  facts_claims__dedup: (data) => (
    <ClaimsDedupReport claimsReport={extractClaimsReport(data)} />
  ),
  facts_claims__evidence: () => (
    <p data-testid="report-facts_claims__evidence" class="text-xs text-muted-foreground">
      Evidence is merged into deduped claims.
    </p>
  ),
  facts_claims__premises: () => (
    <p data-testid="report-facts_claims__premises" class="text-xs text-muted-foreground">
      Premises are merged into deduped claims.
    </p>
  ),
  facts_claims__known_misinfo: (data) => (
    <KnownMisinfoReport matches={extractKnownMisinfo(data)} />
  ),
};

const FACTS_EMPTINESS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => boolean>
> = {
  facts_claims__dedup: (data) => extractClaimsReport(data).deduped_claims.length === 0,
  facts_claims__evidence: (data) =>
    extractClaimsReport(data).deduped_claims.every(
      (claim) => (claim.supporting_facts ?? []).length === 0,
    ),
  facts_claims__premises: (data) =>
    extractClaimsReport(data).deduped_claims.every(
      (claim) => (claim.premise_ids ?? []).length === 0,
    ),
  facts_claims__known_misinfo: (data) => extractKnownMisinfo(data).length === 0,
};

const FACTS_COUNTS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => SlotCountBadge>
> = {
  facts_claims__dedup: (data) => {
    const total = extractClaimsReport(data).deduped_claims.length;
    return { total };
  },
  facts_claims__evidence: (data) => {
    const total = extractClaimsReport(data).deduped_claims.reduce(
      (count, claim) => count + (claim.supporting_facts ?? []).length,
      0,
    );
    return { total };
  },
  facts_claims__premises: (data) => {
    const total = extractClaimsReport(data).deduped_claims.reduce(
      (count, claim) => count + (claim.premise_ids ?? []).length,
      0,
    );
    return { total };
  },
  facts_claims__known_misinfo: (data) => {
    const total = extractKnownMisinfo(data).length;
    return { total };
  },
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
  opinions_sentiments__trends_oppositions: (data) => (
    <TrendsOppositionsReport
      report={extractTrendsOppositionsReport(data)}
    />
  ),
};

const OPINIONS_EMPTINESS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => boolean>
> = {
  opinions_sentiments__sentiment: (data) => {
    const stats = extractSentimentStats(data);
    return (
      stats.per_utterance.length === 0 &&
      stats.positive_pct === 0 &&
      stats.negative_pct === 0 &&
      stats.mean_valence === 0
    );
  },
  opinions_sentiments__subjective: (data) =>
    extractSubjectiveClaims(data).length === 0,
  opinions_sentiments__trends_oppositions: (data) => {
    const report = extractTrendsOppositionsReport(data);
    return report.trends.length === 0 && report.oppositions.length === 0;
  },
};

const OPINIONS_COUNTS: Partial<
  Record<SectionSlugLiteral, (data: unknown) => SlotCountBadge>
> = {
  opinions_sentiments__sentiment: (data) => {
    const total = extractSentimentStats(data).per_utterance.length;
    return { total };
  },
  opinions_sentiments__subjective: (data) => {
    const total = extractSubjectiveClaims(data).length;
    return { total };
  },
  opinions_sentiments__trends_oppositions: (data) => {
    const report = extractTrendsOppositionsReport(data);
    return { total: report.trends.length + report.oppositions.length };
  },
};

function fillMissingSlotsAsRunning(base: SlugToSlots): SlugToSlots {
  // During the early `extracting` / `analyzing` phases the orchestrator may
  // not have seeded sections yet, so `base` is typically `{}`. We synthesize a `running`
  // slot for every known slug so the existing per-slug Skeleton renders
  // immediately. Once `analyzing` starts and the server populates a slot
  // (with state `pending` / `running` / `done`), we honor that slot —
  // the synthesized one is replaced in-place, and because the same
  // skeleton stays mounted for `running`, the visual handoff is seamless.
  const out: SlugToSlots = { ...base };
  for (const slug of SECTION_SLUGS) {
    if (!out[slug]) {
      out[slug] = { state: "running", attempt_id: "extracting" };
    }
  }
  return out;
}

export default function Sidebar(props: SidebarProps) {
  const canJump = () => props.canJumpToUtterance === true;
  const utterances = (): UtteranceAnchor[] => props.payload?.utterances ?? [];
  const safetyRender = createMemo<
    Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>
  >(() => ({
    ...SAFETY_RENDER,
    safety__moderation: (data) => (
      <SafetyModerationReport
        matches={extractHarmfulContentMatches(data)}
        onUtteranceClick={props.onUtteranceClick}
        canJumpToUtterance={canJump()}
      />
    ),
  }));
  const toneRender = createMemo<
    Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>
  >(() => ({
    tone_dynamics__flashpoint: (data) => (
      <FlashpointReport
        matches={extractFlashpointMatches(data)}
        onUtteranceClick={props.onUtteranceClick}
        canJumpToUtterance={canJump()}
      />
    ),
    tone_dynamics__scd: (data) => (
      <ScdReport
        scd={extractScd(data)}
        upstreamStreamType={props.payload?.utterance_stream_type}
        utterances={utterances()}
        onUtteranceClick={props.onUtteranceClick}
        canJumpToUtterance={canJump()}
      />
    ),
  }));
  const factsRender = createMemo<
    Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>
  >(() => ({
    facts_claims__dedup: (data) => (
      <ClaimsDedupReport
        claimsReport={mergeClaimsReportEnrichments(
          extractClaimsReport(data),
          extractClaimsReport(
            effectiveSections().facts_claims__evidence?.data,
          ),
          extractClaimsReport(
            effectiveSections().facts_claims__premises?.data,
          ),
        )}
        onUtteranceClick={props.onUtteranceClick}
        canJumpToUtterance={canJump()}
        evidenceComplete={
          effectiveSections().facts_claims__evidence?.state === "done"
        }
      />
    ),
    facts_claims__evidence: () => (
      <p data-testid="report-facts_claims__evidence" class="text-xs text-muted-foreground">
        Evidence is merged into deduped claims.
      </p>
    ),
    facts_claims__premises: () => (
      <p data-testid="report-facts_claims__premises" class="text-xs text-muted-foreground">
        Premises are merged into deduped claims.
      </p>
    ),
    facts_claims__known_misinfo: (data) => (
      <KnownMisinfoReport matches={extractKnownMisinfo(data)} />
    ),
  }));
  const opinionsRender = createMemo<
    Partial<Record<SectionSlugLiteral, (data: unknown) => JSX.Element>>
  >(() => ({
    opinions_sentiments__sentiment: (data) => (
      <SentimentReport stats={extractSentimentStats(data)} />
    ),
    opinions_sentiments__subjective: (data) => (
      <SubjectiveReport
        claims={extractSubjectiveClaims(data)}
        onUtteranceClick={props.onUtteranceClick}
        canJumpToUtterance={canJump()}
      />
    ),
    opinions_sentiments__trends_oppositions: (data) => (
      <TrendsOppositionsReport
        report={extractTrendsOppositionsReport(data)}
      />
    ),
  }));
  const effectiveSections = createMemo<SlugToSlots>(() => {
    const raw = props.sections;
    const hasSlots = raw !== undefined && Object.keys(raw).length > 0;
    const isTerminal =
      props.jobStatus === "done" ||
      props.jobStatus === "partial" ||
      props.jobStatus === "failed";
    const shouldSynthesize =
      props.payloadComplete === true ||
      (isTerminal && !hasSlots && props.payload != null);
    const baseline = hasSlots
      ? asStrictSectionSlots(raw)
      : shouldSynthesize && props.payload
        ? synthesizeSectionsFromPayload(props.payload)
        : {};
    if (props.jobStatus === "extracting" || props.jobStatus === "analyzing") {
      return fillMissingSlotsAsRunning(baseline);
    }
    return baseline;
  });
  const partialFailedSlugs = createMemo(() =>
    props.jobStatus === "partial"
      ? SECTION_SLUGS.filter(
          (slug) => effectiveSections()[slug]?.state === "failed",
        )
      : [],
  );
  const safetyRecommendation = createMemo<SafetyRecommendation | null>(() =>
    props.payloadComplete === true
      ? (props.payload?.safety?.recommendation ?? null)
      : null,
  );
  const safetySummary = createMemo(() => {
    const recommendation = safetyRecommendation();
    if (!recommendation) return undefined;
    return {
      label: "Summary",
      defaultOpen: true,
      content: () => (
        <SafetyRecommendationReport recommendation={recommendation} />
      ),
    };
  });

  return (
    <aside
      aria-label="Analysis sidebar"
      data-testid="analysis-sidebar"
      data-job-status={props.jobStatus ?? ""}
      class={`flex w-full flex-col gap-4 ${props.class ?? ""}`}
    >
      <Show
        when={
          props.jobStatus === "extracting" || props.jobStatus === "analyzing"
        }
      >
        <ExtractingIndicator
          activityLabel={props.activityLabel}
          activityAt={props.activityAt}
        />
      </Show>
      <Show when={partialFailedSlugs().length > 0}>
        <div
          data-testid="partial-failure-banner"
          class="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          Some sections could not run:{" "}
          {partialFailedSlugs().map(sectionDisplayName).join(", ")}
        </div>
      </Show>
      <SectionGroup
        label="Safety"
        slugs={SAFETY_SLUGS}
        sections={effectiveSections()}
        render={safetyRender()}
        summary={safetySummary()}
        emptinessChecks={SAFETY_EMPTINESS}
        counts={SAFETY_COUNTS}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
        renderRevision={canJump()}
      />
      <SectionGroup
        label="Tone/dynamics"
        slugs={TONE_SLUGS}
        sections={effectiveSections()}
        render={toneRender()}
        emptinessChecks={TONE_EMPTINESS}
        counts={TONE_COUNTS}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
        renderRevision={canJump()}
      />
      <SectionGroup
        label="Facts/claims"
        slugs={FACTS_SLUGS}
        sections={effectiveSections()}
        render={factsRender()}
        emptinessChecks={FACTS_EMPTINESS}
        counts={FACTS_COUNTS}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
        renderRevision={`${canJump()}:${
          effectiveSections().facts_claims__evidence?.attempt_id ?? ""
        }:${
          effectiveSections().facts_claims__evidence?.state ?? ""
        }:${
          effectiveSections().facts_claims__premises?.attempt_id ?? ""
        }:${
          effectiveSections().facts_claims__premises?.state ?? ""
        }`}
      />
      <SectionGroup
        label="Opinions/sentiments"
        slugs={OPINIONS_SLUGS}
        sections={effectiveSections()}
        render={opinionsRender()}
        emptinessChecks={OPINIONS_EMPTINESS}
        counts={OPINIONS_COUNTS}
        jobId={props.jobId}
        onRetry={props.onRetry}
        cachedHint={props.cachedHint}
        renderRevision={canJump()}
      />
    </aside>
  );
}
