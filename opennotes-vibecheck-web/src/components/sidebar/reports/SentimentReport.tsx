import type { components } from "~/lib/generated-types";
import SentimentTimelineSection from "./sentiment-timeline/SentimentTimelineSection";
import { FeedbackBell } from "../../feedback/FeedbackBell";

type SentimentStats = components["schemas"]["SentimentStatsReport"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

export interface SentimentReportProps {
  stats: SentimentStats;
  anchors: UtteranceAnchor[];
}

function clampPct(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value <= 0) return 0;
  if (value >= 100) return 100;
  return value;
}

export default function SentimentReport(props: SentimentReportProps) {
  const normalized = () => {
    const pos = clampPct(props.stats.positive_pct);
    const neg = clampPct(props.stats.negative_pct);
    const neu = clampPct(props.stats.neutral_pct);
    const total = pos + neg + neu;
    const scale = total > 100 ? 100 / total : 1;
    return {
      positive: Math.round(pos * scale),
      negative: Math.round(neg * scale),
      neutral: Math.round(neu * scale),
    };
  };
  const positive = () => normalized().positive;
  const negative = () => normalized().negative;
  const neutral = () => normalized().neutral;

  return (
    <div
      data-testid="report-opinions_sentiments__sentiment"
      class="relative space-y-2"
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
      <SentimentTimelineSection
        scores={props.stats.per_utterance}
        anchors={props.anchors}
      />
      <FeedbackBell bell_location="card:sentiment" />
    </div>
  );
}
