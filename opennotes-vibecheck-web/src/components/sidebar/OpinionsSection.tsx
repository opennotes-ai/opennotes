import { For, Show } from "solid-js";
import type { components } from "~/lib/generated-types";

type OpinionsPayload = components["schemas"]["OpinionsSection"];
type SentimentStats = components["schemas"]["SentimentStatsReport"];
type SubjectiveClaim = components["schemas"]["SubjectiveClaim"];

export interface OpinionsSectionProps {
  opinions: OpinionsPayload;
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value <= 0) return 0;
  if (value >= 100) return 100;
  return Math.round(value);
}

function formatValence(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  const sign = rounded > 0 ? "+" : "";
  return `${sign}${rounded.toFixed(2)}`;
}

function SentimentBar(props: { stats: SentimentStats }) {
  const positive = () => clampPct(props.stats.positive_pct);
  const negative = () => clampPct(props.stats.negative_pct);
  const neutral = () => Math.max(0, 100 - positive() - negative());

  return (
    <div
      data-testid="sentiment-entry"
      class="space-y-2 border-l-2 border-chart-5 pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Sentiment
      </p>
      <div
        role="img"
        aria-label={`Sentiment: ${positive()}% positive, ${negative()}% negative, ${neutral()}% neutral`}
        class="flex h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          class="h-full bg-chart-1"
          style={{ width: `${positive()}%` }}
          data-testid="sentiment-positive"
        />
        <div
          class="h-full bg-chart-4"
          style={{ width: `${negative()}%` }}
          data-testid="sentiment-negative"
        />
        <div
          class="h-full bg-muted-foreground/40"
          style={{ width: `${neutral()}%` }}
          data-testid="sentiment-neutral"
        />
      </div>
      <dl class="grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
        <div>
          <dt class="font-semibold text-foreground">+ {positive()}%</dt>
          <dd>positive</dd>
        </div>
        <div>
          <dt class="font-semibold text-foreground">- {negative()}%</dt>
          <dd>negative</dd>
        </div>
        <div>
          <dt class="font-semibold text-foreground">{neutral()}%</dt>
          <dd>neutral</dd>
        </div>
      </dl>
      <p class="text-[11px] text-muted-foreground">
        mean valence{" "}
        <span
          data-testid="sentiment-mean-valence"
          class="font-mono text-foreground"
        >
          {formatValence(props.stats.mean_valence)}
        </span>
      </p>
    </div>
  );
}

function SubjectiveClaimsList(props: { claims: SubjectiveClaim[] }) {
  return (
    <div
      data-testid="subjective-entry"
      class="space-y-2 border-l-2 border-chart-4 pl-3"
    >
      <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Subjective ({props.claims.length})
      </p>
      <Show
        when={props.claims.length > 0}
        fallback={
          <p class="text-xs text-muted-foreground">
            No subjective claims detected.
          </p>
        }
      >
        <ul class="space-y-1">
          <For each={props.claims}>
            {(claim) => (
              <li
                data-testid="subjective-claim"
                class="text-xs text-foreground"
              >
                <span class="mr-1 inline-flex items-center rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  {claim.stance}
                </span>
                {claim.claim_text}
              </li>
            )}
          </For>
        </ul>
      </Show>
    </div>
  );
}

export default function OpinionsSection(props: OpinionsSectionProps) {
  return (
    <section
      aria-labelledby="sidebar-opinions-heading"
      data-testid="sidebar-opinions"
      class="space-y-3 rounded-lg border border-border bg-card p-4"
    >
      <header>
        <h3
          id="sidebar-opinions-heading"
          class="flex items-center gap-2 text-sm font-semibold text-foreground"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          >
            <path d="M2 7c0-3 2.5-5 6-5s6 2 6 5-2.5 5-6 5H5l-2 2v-3c-.6-1.2-1-2.5-1-4z" />
          </svg>
          Opinions &amp; sentiments
        </h3>
      </header>

      <div class="space-y-3">
        <SentimentBar stats={props.opinions.opinions_report.sentiment_stats} />
        <SubjectiveClaimsList
          claims={props.opinions.opinions_report.subjective_claims}
        />
      </div>
    </section>
  );
}
