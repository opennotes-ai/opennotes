import { Show, type JSX } from "solid-js";
import { Card } from "@opennotes/ui/components/ui/card";
import type { components } from "~/lib/generated-types";

type SafetyRecommendation = components["schemas"]["SafetyRecommendation"];
type SafetyLevel = components["schemas"]["SafetyLevel"];
type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type RiskLevel = components["schemas"]["RiskLevel"];
type WeatherReport = components["schemas"]["WeatherReport"];
type RelevanceLabel = WeatherReport["relevance"]["label"];

export type OverallVerdict = "pass" | "flag";
export type OverallDecision = components["schemas"]["OverallDecision"];

// The set of signals the overall verdict is decided over. The verdict is a
// cost-benefit decision — "should a moderator intervene?" — weighing
// risk signals (what's the cost of NOT intervening?) against utility signals
// (what's the benefit of intervening — is the content worth the effort?).
//
// Slots are grouped by level: higher-level slots carry already-synthesized
// agent outputs; lower-level slots carry raw analyzer findings. The server
// overall-recommendation agent now owns this synthesis when `overall` is
// present; this web-side signal bag remains the deterministic fallback.
export interface OverallSignals {
  // Risk side — higher-level synthesized agent outputs.
  safetyRecommendation: SafetyRecommendation | null;
  flashpointMatches?: FlashpointMatch[] | null;
  // Utility side — "weather report" axes about whether the content is
  // worth a moderator's attention.
  utility?: {
    weatherReport?: WeatherReport | null;
  };
  // Lower-level: raw per-analyzer findings. Reserved slot, intentionally
  // empty for now.
  lowLevel?: Record<string, never>;
}

export interface OverallRecommendationCardProps {
  recommendation: SafetyRecommendation | null;
  overall?: OverallDecision | null;
  flashpointMatches?: FlashpointMatch[] | null;
  weatherReport?: WeatherReport | null;
}

const HIGH_FLASHPOINT_LEVELS: RiskLevel[] = ["Heated", "Hostile", "Dangerous"];
const FLASHPOINT_PRIORITY: Record<RiskLevel, number> = {
  "Low Risk": 0,
  Guarded: 1,
  Heated: 2,
  Hostile: 3,
  Dangerous: 4,
};

function highestFlashpointRisk(
  matches: FlashpointMatch[] | null | undefined,
): RiskLevel | null {
  if (!matches || matches.length === 0) return null;
  let highest: RiskLevel | null = null;
  for (const match of matches) {
    if (!HIGH_FLASHPOINT_LEVELS.includes(match.risk_level)) continue;
    if (
      highest === null ||
      FLASHPOINT_PRIORITY[match.risk_level] > FLASHPOINT_PRIORITY[highest]
    ) {
      highest = match.risk_level;
    }
  }
  return highest;
}

export function escalateForFlashpoint(
  base: OverallDecision | null,
  recommendation: SafetyRecommendation | null,
  flashpointMatches: FlashpointMatch[] | null | undefined,
): OverallDecision | null {
  if (base === null) return null;
  if (base.verdict !== "pass") return base;
  if (recommendation?.level !== "mild") return base;
  const highest = highestFlashpointRisk(flashpointMatches);
  if (highest === null) return base;
  return {
    verdict: "flag",
    reason: `Conversation flashpoint risk: ${highest}`,
    status: "final",
  };
}

const ON_TOPIC_RELEVANCE: RelevanceLabel[] = ["insightful", "on_topic"];

// Cost-benefit rule: a Pass decision should escalate when the page is
// on-topic enough to be worth a moderator's attention AND the truth axis
// flags misleading framing. Only escalates Pass — never downgrades Flag.
export function escalateForMisleadingOnTopic(
  base: OverallDecision | null,
  weatherReport: WeatherReport | null | undefined,
): OverallDecision | null {
  if (base === null) return null;
  if (base.verdict !== "pass") return base;
  if (!weatherReport) return base;
  if (weatherReport.truth.label !== "misleading") return base;
  if (!ON_TOPIC_RELEVANCE.includes(weatherReport.relevance.label)) return base;
  return {
    verdict: "flag",
    reason: "Misleading framing in on-topic discussion",
    status: "final",
  };
}

const PASS_LEVELS: SafetyLevel[] = ["safe", "mild"];

function verdictFromLevel(level: SafetyLevel): OverallVerdict {
  return PASS_LEVELS.includes(level) ? "pass" : "flag";
}

function isFalsePositiveRationale(text: string): boolean {
  return /false positives?|judged (?:to be )?false positives?|dismissed/i.test(
    text,
  );
}

function isRawModerationScoreSignal(text: string): boolean {
  const stripped = text.trim();
  // Prefix-form: text:/image:/video: followed by a category-ish body ending
  // in a decimal score (e.g. "image: max_likelihood 0.25", "text: Firearms &
  // Weapons 0.769"). The body excludes digits to keep the match linear and
  // avoid quadratic backtracking on malformed input.
  if (/^(?:text|image|video)\s*:\s*[^\d\s][^\d]*\d+\.\d+$/i.test(stripped)) {
    return true;
  }
  // No-prefix form: a short label-shaped string followed by a final decimal,
  // e.g. "Firearms & Weapons 0.769" or "Death, Harm & Tragedy 0.85". Char
  // class allows letters, spaces, '&', ',', '/', '-', and apostrophe so GCP
  // categories like "Children's Interests" or "War & Conflict" match too.
  return /^[a-z][a-z &,/'\-]*\s+(?:score\s+)?\d+\.\d+$/i.test(stripped);
}

function clauseContainsRawScore(clause: string): boolean {
  // Catches embedded decimals like "Legal 1.0" or "0.769" inside a longer
  // sentence — the suppress path should skip these clauses entirely, not
  // just clauses that are themselves raw signals.
  return /\d+\.\d+/.test(clause);
}

function isMeaningfulClause(clause: string): boolean {
  // Reject single-letter / single-token fragments left over from splitting
  // abbreviations ("e.g.", "i.e.", "U.S.") that slipped through the
  // protect-abbreviations pass. A useful reason needs at least two
  // alphabetic words.
  const words = clause.match(/[A-Za-z]{2,}/g) ?? [];
  return words.length >= 2;
}

function protectAbbreviations(rationale: string): string {
  // Drop parenthetical example asides like "(e.g., Rust, Julia)" — they
  // are decoration and a frequent source of split-fragment garbage (the
  // "e.g." abbreviation getting torn into single-letter clauses). Keep
  // other parentheticals so qualifiers like "(Legal 1.0)" still scope
  // adjacent false-positive language to the right clause.
  return rationale
    .replace(/\s*\((?:e\.g\.|i\.e\.|etc\.|cf\.)[^()]*\)/gi, "")
    .replace(/\b(?:e\.g\.|i\.e\.|etc\.|cf\.|vs\.|Mr\.|Mrs\.|Ms\.|Dr\.|U\.S\.)/gi, "");
}

function rationaleConcernClauses(rationale: string): string[] {
  return protectAbbreviations(rationale)
    // Split on sentence-ending '.' and ';' but NOT on decimals like "1.0".
    // Also split on " but " / ", but " to break compound concession clauses.
    .split(/(?<!\d)\.(?!\d)|;|\s*,\s*but\s+|\s+but\s+/i)
    .map((clause) => clause.trim())
    .filter((clause) => clause.length > 0)
    .filter((clause) => !isFalsePositiveRationale(clause))
    .filter((clause) => !isRawModerationScoreSignal(clause))
    .filter((clause) => !clauseContainsRawScore(clause))
    .filter((clause) => isMeaningfulClause(clause));
}

function levelFallbackReason(level: SafetyLevel): string {
  switch (level) {
    case "safe":
      return "No notable safety concerns";
    case "mild":
      return "Minor concerns noted";
    case "caution":
      return "Multiple low-severity concerns";
    case "unsafe":
      return "Significant safety concerns";
  }
}

function deriveReason(recommendation: SafetyRecommendation): string | null {
  const signals = recommendation.top_signals;
  const rationale = recommendation.rationale.trim();
  const hasRawScoreSignal = signals?.some((signal) =>
    isRawModerationScoreSignal(signal),
  ) ?? false;
  const suppressRawScoreSignals =
    hasRawScoreSignal && isFalsePositiveRationale(rationale);
  if (signals && signals.length > 0) {
    const firstSignal = signals
      .map((signal) => signal.trim())
      .find(
        (signal) =>
          signal.length > 0 &&
          (!suppressRawScoreSignals || !isRawModerationScoreSignal(signal)),
      );
    if (firstSignal !== undefined) {
      return firstSignal;
    }
  }
  if (!rationale) {
    return null;
  }
  if (suppressRawScoreSignals) {
    const concernClause = rationaleConcernClauses(rationale)[0];
    if (concernClause) {
      return concernClause;
    }
    return levelFallbackReason(recommendation.level);
  }
  const firstClause = rationale.split(/[,.]/, 1)[0] ?? rationale;
  const trimmedClause = firstClause.trim();
  if (!trimmedClause) {
    return null;
  }
  return trimmedClause;
}

function decideFromSafety(
  recommendation: SafetyRecommendation,
): OverallDecision | null {
  const reason = deriveReason(recommendation);
  if (reason === null) {
    return null;
  }
  return {
    verdict: verdictFromLevel(recommendation.level),
    reason,
    status: "final",
  };
}

// Fallback decision over the cross-signal bag when the server has not supplied
// an OverallDecision. The function is a cost-benefit composition: should a
// moderator intervene, given the risk signals (cost of NOT intervening) and
// the utility signals (benefit of intervening — is the content worth it)?
//
// Rules layer in priority order:
//   1. Risk-side base: the higher-level safety recommendation (agent
//      synthesis of lower-level moderation / web-risk / image / video
//      findings).
//   2. Risk-side escalation: tone dynamics promotes mild safety to flag
//      when the conversation flashpoint detector disagrees.
//   3. Utility-side escalation: misleading framing in on-topic discussion
//      promotes pass to flag, because the content is worth a moderator's
//      attention.
//   4. (Future rules over lower-level signals layer in here.)
//
// Keep this web-side path alive for old/null server responses; see
// `docs/architecture/overall-verdict-cross-signal-escalation.md`.
export function decideOverall(
  signals: OverallSignals,
): OverallDecision | null {
  if (signals.safetyRecommendation === null) {
    return null;
  }
  const base = decideFromSafety(signals.safetyRecommendation);
  const afterFlashpoint = escalateForFlashpoint(
    base,
    signals.safetyRecommendation,
    signals.flashpointMatches,
  );
  return escalateForMisleadingOnTopic(
    afterFlashpoint,
    signals.utility?.weatherReport,
  );
}

const VERDICT_CLASSES: Record<OverallVerdict, string> = {
  pass: "bg-muted text-muted-foreground border-border",
  flag: "bg-destructive/5 text-destructive border-destructive/40",
};

export function OverallRecommendationCard(
  props: OverallRecommendationCardProps,
): JSX.Element | null {
  const resolved = (): OverallDecision | null => {
    if (props.overall != null) return props.overall;
    return decideOverall({
      safetyRecommendation: props.recommendation,
      flashpointMatches: props.flashpointMatches,
      utility: { weatherReport: props.weatherReport },
    });
  };

  return (
    <Show when={resolved()}>
      {(data) => (
        <Card
          data-testid="overall-recommendation-card"
          class={`flex items-center gap-2 border p-3 text-sm font-semibold ${VERDICT_CLASSES[data().verdict]}`}
        >
          <span data-testid="overall-recommendation-verdict" class="shrink-0">
            {data().verdict === "pass" ? "Overall: OK." : "Overall: Flag!"}
          </span>
          <span
            data-testid="overall-recommendation-reason"
            class="font-normal min-w-0 flex-1 truncate"
            title={data().reason}
          >
            {data().reason}
          </span>
        </Card>
      )}
    </Show>
  );
}
