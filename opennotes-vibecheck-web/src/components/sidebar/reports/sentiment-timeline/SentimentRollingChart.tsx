import { EChart } from "@opennotes/ui/components/ui/echart";
import type { SentimentBucket } from "~/lib/sentiment-buckets";
import { buildRollingOption } from "./buildRollingOption";

export interface SentimentRollingChartProps {
  buckets: SentimentBucket[];
  height?: string;
}

export default function SentimentRollingChart(props: SentimentRollingChartProps) {
  return (
    <div data-testid="sentiment-rolling-chart">
      <EChart
        option={buildRollingOption(props.buckets)}
        height={props.height ?? "120px"}
      />
    </div>
  );
}
