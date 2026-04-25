import { For, Show, type JSX } from "solid-js";
import type { components } from "~/lib/generated-types";
import ExpandableText from "../ExpandableText";

type FlashpointMatch = components["schemas"]["FlashpointMatch"];
type RiskLevel = components["schemas"]["RiskLevel"];

const RISK_PHRASES: Record<RiskLevel, string> = {
  Dangerous: "a dangerous flashpoint",
  Hostile: "a sharp clash",
  Heated: "a heated exchange",
  Guarded: "a brief tense moment",
  "Low Risk": "a brief tense moment",
};

const RISK_QUALIFIERS: Record<RiskLevel, string> = {
  Dangerous: "severe risk",
  Hostile: "high risk",
  Heated: "moderate risk",
  Guarded: "low risk",
  "Low Risk": "low risk",
};

function phraseFor(level: RiskLevel): string {
  return RISK_PHRASES[level] ?? "a tense moment";
}

function qualifierFor(level: RiskLevel): string {
  return RISK_QUALIFIERS[level] ?? "elevated risk";
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "derailment unavailable";
  return `derailment ~${Math.round(score)}/100`;
}

export interface FlashpointReportProps {
  matches: FlashpointMatch[];
}

export default function FlashpointReport(
  props: FlashpointReportProps,
): JSX.Element {
  const matches = (): FlashpointMatch[] => props.matches ?? [];

  return (
    <div data-testid="report-tone_dynamics__flashpoint" class="space-y-3">
      <Show
        when={matches().length > 0}
        fallback={
          <p
            data-testid="flashpoint-empty"
            class="text-xs text-muted-foreground"
          >
            Things stay even-keeled across this thread.
          </p>
        }
      >
        <ul class="space-y-3">
          <For each={matches()}>
            {(match) => (
              <li data-testid="flashpoint-entry" class="space-y-1">
                <p
                  data-testid="flashpoint-headline"
                  class="text-xs text-foreground"
                >
                  {phraseFor(match.risk_level)} around turn{" "}
                  {match.utterance_id} &mdash; {qualifierFor(match.risk_level)}.
                </p>
                <p
                  data-testid="flashpoint-score"
                  class="font-mono text-[10px] text-muted-foreground"
                >
                  {formatScore(match.derailment_score)}
                </p>
                <ExpandableText
                  text={match.reasoning}
                  lines={2}
                  testId="flashpoint-reasoning"
                  class="text-xs text-muted-foreground"
                />
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}
