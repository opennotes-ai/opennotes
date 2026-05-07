import { EChart } from "@opennotes/ui/components/ui/echart";
import type { SentimentBucket } from "~/lib/sentiment-buckets";
import { buildPunchCardOption } from "./buildPunchCardOption";

export interface SentimentPunchCardChartProps {
  buckets: SentimentBucket[];
  height?: string;
}

export default function SentimentPunchCardChart(
  props: SentimentPunchCardChartProps,
) {
  return (
    <div data-testid="sentiment-punch-card-chart">
      <EChart
        option={buildPunchCardOption(props.buckets)}
        height={props.height ?? "90px"}
      />
    </div>
  );
}
