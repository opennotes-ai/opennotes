import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import { humanizeLabel, softHyphenate } from "@opennotes/ui/utils";
import { TIER_DESCRIPTIONS, TERM_DESCRIPTIONS } from "@opennotes/ui/palettes";
import SectionHeader from "@opennotes/ui/components/ui/section-header";

type ConsensusMetricsData = components["schemas"]["ConsensusMetricsData"];
type ScoringCoverageData = components["schemas"]["ScoringCoverageData"];

export default function ScoringAnalysisSection(props: {
  consensus: ConsensusMetricsData;
  scoring: ScoringCoverageData;
}) {
  const tierDistribution = createMemo(() => Object.entries(props.scoring.tier_distribution));
  const scorerBreakdown = createMemo(() => Object.entries(props.scoring.scorer_breakdown));

  return (
    <section id="scoring-analysis">
      <SectionHeader title="Scoring & Consensus" subtitle="How the community reached (or failed to reach) agreement" />

      <div class="mt-4 flex flex-wrap gap-2">
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm" title={TERM_DESCRIPTIONS.mean_agreement} tabindex="0"><span class="text-muted-foreground">Agreement:</span> <strong>{props.consensus.mean_agreement.toFixed(3)}</strong></span>
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm" title={TERM_DESCRIPTIONS.polarization_index} tabindex="0"><span class="text-muted-foreground">Polarization:</span> <strong>{props.consensus.polarization_index.toFixed(3)}</strong></span>
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm" title={TERM_DESCRIPTIONS.notes_with_consensus} tabindex="0"><span class="text-muted-foreground">Consensus:</span> <strong>{props.consensus.notes_with_consensus}</strong></span>
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm" title={TERM_DESCRIPTIONS.notes_with_disagreement} tabindex="0"><span class="text-muted-foreground">Disagreement:</span> <strong>{props.consensus.notes_with_disagreement}</strong></span>
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm" title={TERM_DESCRIPTIONS.total_notes_rated} tabindex="0"><span class="text-muted-foreground">Total Rated:</span> <strong>{props.consensus.total_notes_rated}</strong></span>
      </div>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Scoring Coverage</h3>
      <div class="mt-2 flex flex-wrap gap-2">
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm"><span class="text-muted-foreground">Tier:</span> <strong>{humanizeLabel(props.scoring.current_tier)}</strong></span>
        <span class="rounded-md bg-muted/50 px-3 py-2 text-sm"><span class="text-muted-foreground">Scores:</span> <strong>{props.scoring.total_scores_computed}</strong></span>
      </div>
      <Show when={TIER_DESCRIPTIONS[props.scoring.current_tier]}>
        {(tierInfo) => (
          <p class="mt-2 text-sm text-muted-foreground">
            <strong class="text-foreground">{tierInfo().label}</strong>: {tierInfo().description}{" "}
            {tierInfo().helpfulnessNote}
          </p>
        )}
      </Show>

      <div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg border border-border p-4">
          <h3 class="mb-2 text-sm font-semibold">Tier Distribution</h3>
          <table class="w-full text-sm" aria-label="Tier distribution">
            <tbody>
              <For each={tierDistribution()}>
                {([tier, count]) => {
                  const tierInfo = () => TIER_DESCRIPTIONS[tier];
                  return (
                    <tr class="border-b border-border last:border-0">
                      <td class="py-1 text-muted-foreground" tabindex="0" title={tierInfo()?.description ?? ""} aria-label={`${humanizeLabel(tier)}: ${tierInfo()?.description ?? "No description"}`}>
                        {humanizeLabel(tier)}
                      </td>
                      <td class="py-1 text-right font-medium">{count}</td>
                    </tr>
                  );
                }}
              </For>
            </tbody>
          </table>
        </div>
        <div class="rounded-lg border border-border p-4">
          <h3 class="mb-2 text-sm font-semibold">Scorer Breakdown</h3>
          <table class="w-full text-sm" aria-label="Scorer breakdown">
            <tbody>
              <For each={scorerBreakdown()}>
                {([scorer, count]) => (
                  <tr class="border-b border-border last:border-0">
                    <td class="py-1 text-muted-foreground break-words">{softHyphenate(scorer)}</td>
                    <td class="py-1 text-right font-medium">{count}</td>
                  </tr>
                )}
              </For>
            </tbody>
          </table>
        </div>
        <div class="rounded-lg border border-border p-4">
          <h3 class="mb-2 text-sm font-semibold">Tiers Reached</h3>
          <p class="text-sm text-muted-foreground">
            {props.scoring.tiers_reached.map(humanizeLabel).join(", ") || "None"}
          </p>
        </div>
        <div class="rounded-lg border border-border p-4">
          <h3 class="mb-2 text-sm font-semibold">Scorers Exercised</h3>
          <p class="text-sm text-muted-foreground break-words">
            {props.scoring.scorers_exercised.map(softHyphenate).join(", ") || "None"}
          </p>
        </div>
      </div>
    </section>
  );
}
