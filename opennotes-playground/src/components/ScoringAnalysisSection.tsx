import { For, Show, createMemo } from "solid-js";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import { TIER_DESCRIPTIONS } from "~/lib/scoring-tiers";
import { softHyphenate } from "~/lib/soft-hyphenate";

type ConsensusMetricsData = components["schemas"]["ConsensusMetricsData"];
type ScoringCoverageData = components["schemas"]["ScoringCoverageData"];

function MetricCard(props: { label: string; value: string }) {
  return (
    <div class="rounded-lg border border-border bg-card p-3">
      <div class="text-xs text-muted-foreground">{props.label}</div>
      <div class="mt-1 text-xl font-semibold">{props.value}</div>
    </div>
  );
}

export default function ScoringAnalysisSection(props: {
  consensus: ConsensusMetricsData;
  scoring: ScoringCoverageData;
}) {
  const tierDistribution = createMemo(() => Object.entries(props.scoring.tier_distribution));
  const scorerBreakdown = createMemo(() => Object.entries(props.scoring.scorer_breakdown));

  return (
    <section id="scoring-analysis">
      <h2 class="mb-4 text-xl font-semibold">Scoring & Analysis</h2>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Consensus</h3>
      <div class="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        <MetricCard label="Mean Agreement" value={props.consensus.mean_agreement.toFixed(3)} />
        <MetricCard label="Polarization Index" value={props.consensus.polarization_index.toFixed(3)} />
        <MetricCard label="With Consensus" value={String(props.consensus.notes_with_consensus)} />
        <MetricCard label="With Disagreement" value={String(props.consensus.notes_with_disagreement)} />
        <MetricCard label="Total Rated" value={String(props.consensus.total_notes_rated)} />
      </div>

      <h3 class="mt-6 text-sm font-medium text-muted-foreground">Scoring Coverage</h3>
      <div class="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        <MetricCard label="Current Tier" value={humanizeLabel(props.scoring.current_tier)} />
        <MetricCard label="Scores Computed" value={String(props.scoring.total_scores_computed)} />
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
        <div class="rounded-lg border border-border bg-card p-4">
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
        <div class="rounded-lg border border-border bg-card p-4">
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
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-semibold">Tiers Reached</h3>
          <p class="text-sm text-muted-foreground">
            {props.scoring.tiers_reached.map(humanizeLabel).join(", ") || "None"}
          </p>
        </div>
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-semibold">Scorers Exercised</h3>
          <p class="text-sm text-muted-foreground break-words">
            {props.scoring.scorers_exercised.map(softHyphenate).join(", ") || "None"}
          </p>
        </div>
      </div>
    </section>
  );
}
