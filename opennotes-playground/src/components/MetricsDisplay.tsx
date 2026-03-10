import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";
import { humanizeLabel } from "~/lib/format";
import { TIER_DESCRIPTIONS } from "~/lib/scoring-tiers";

type ConsensusMetricsData = components["schemas"]["ConsensusMetricsData"];
type ScoringCoverageData = components["schemas"]["ScoringCoverageData"];

export default function MetricsDisplay(props: {
  consensus: ConsensusMetricsData;
  scoring: ScoringCoverageData;
}) {
  return (
    <section>
      <h2 class="mb-4 text-xl font-semibold">Consensus Metrics</h2>
      <div class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
        <MetricCard label="Mean Agreement" value={props.consensus.mean_agreement.toFixed(3)} />
        <MetricCard label="Polarization Index" value={props.consensus.polarization_index.toFixed(3)} />
        <MetricCard label="With Consensus" value={String(props.consensus.notes_with_consensus)} />
        <MetricCard label="With Disagreement" value={String(props.consensus.notes_with_disagreement)} />
        <MetricCard label="Total Rated" value={String(props.consensus.total_notes_rated)} />
      </div>

      <h2 class="mb-4 text-xl font-semibold">Scoring Coverage</h2>
      <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
        <MetricCard label="Current Tier" value={humanizeLabel(props.scoring.current_tier)} />
        <MetricCard label="Scores Computed" value={String(props.scoring.total_scores_computed)} />
      </div>
      <Show when={TIER_DESCRIPTIONS[props.scoring.current_tier]}>
        {(tierInfo) => (
          <p class="mb-6 text-sm text-muted-foreground">
            <strong class="text-foreground">{tierInfo().label}</strong>: {tierInfo().description}{" "}
            {tierInfo().helpfulnessNote}
          </p>
        )}
      </Show>

      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg border border-border bg-card p-4">
          <h3 class="mb-2 text-sm font-semibold">Tier Distribution</h3>
          <table class="w-full text-sm" aria-label="Tier distribution">
            <tbody>
              <For each={Object.entries(props.scoring.tier_distribution)}>
                {([tier, count]) => {
                  const tierInfo = () => TIER_DESCRIPTIONS[tier];
                  return (
                    <tr class="border-b border-border last:border-0">
                      <td class="py-1 text-muted-foreground" title={tierInfo()?.description ?? ""} aria-label={`${humanizeLabel(tier)}: ${tierInfo()?.description ?? "No description"}`}>
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
              <For each={Object.entries(props.scoring.scorer_breakdown)}>
                {([scorer, count]) => (
                  <tr class="border-b border-border last:border-0">
                    <td class="py-1 text-muted-foreground">{scorer}</td>
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
          <p class="text-sm text-muted-foreground">
            {props.scoring.scorers_exercised.join(", ") || "None"}
          </p>
        </div>
      </div>
    </section>
  );
}

function MetricCard(props: { label: string; value: string }) {
  return (
    <div class="rounded-lg border border-border bg-card p-3">
      <div class="text-xs text-muted-foreground">{props.label}</div>
      <div class="mt-1 text-xl font-semibold">{props.value}</div>
    </div>
  );
}
