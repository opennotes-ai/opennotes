import type { components } from "~/lib/generated-types";

type SentimentStats = components["schemas"]["SentimentStatsReport"];

export interface SentimentReportProps {
  stats: SentimentStats;
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

export default function SentimentReport(props: SentimentReportProps) {
  const positive = () => clampPct(props.stats.positive_pct);
  const negative = () => clampPct(props.stats.negative_pct);
  const neutral = () => clampPct(props.stats.neutral_pct);

  return (
    <div
      data-testid="report-opinions_sentiments__sentiment"
      class="space-y-2"
    >
      <div
        role="img"
        aria-label={`Sentiment: ${positive()}% positive, ${negative()}% negative, ${neutral()}% neutral`}
        class="flex h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          class="h-full bg-positive"
          style={{ width: `${positive()}%` }}
          data-testid="sentiment-positive"
        />
        <div
          class="h-full bg-negative"
          style={{ width: `${negative()}%` }}
          data-testid="sentiment-negative"
        />
        <div
          class="h-full bg-muted-foreground/40"
          style={{ width: `${neutral()}%` }}
          data-testid="sentiment-neutral"
        />
      </div>
      <dl
        data-testid="sentiment-legend"
        class="grid grid-cols-3 gap-2 text-center text-[11px] text-muted-foreground justify-items-center"
      >
        <div>
          <dt class="font-semibold text-positive" data-testid="sentiment-positive-label">
            {positive()}%
          </dt>
          <dd>positive</dd>
        </div>
        <div>
          <dt class="font-semibold text-negative" data-testid="sentiment-negative-label">
            {negative()}%
          </dt>
          <dd>negative</dd>
        </div>
        <div>
          <dt class="font-semibold text-foreground" data-testid="sentiment-neutral-label">
            {neutral()}%
          </dt>
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
