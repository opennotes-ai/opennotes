import type { components } from "~/lib/generated-types";
import { bucketSentimentByTime } from "~/lib/sentiment-buckets";
import SentimentPunchCardChart from "./SentimentPunchCardChart";
import SentimentRollingChart from "./SentimentRollingChart";

type SentimentScore = components["schemas"]["SentimentScore"];
type UtteranceAnchor = components["schemas"]["UtteranceAnchor"];

export interface SentimentTimelineSectionProps {
  scores: SentimentScore[];
  anchors: UtteranceAnchor[];
}

export default function SentimentTimelineSection(
  props: SentimentTimelineSectionProps,
) {
  const result = () => bucketSentimentByTime(props.scores, props.anchors);

  if (!result().renderable) {
    return null;
  }

  return (
    <div data-testid="sentiment-timeline" class="space-y-1">
      <SentimentRollingChart buckets={result().buckets} />
      <SentimentPunchCardChart buckets={result().buckets} />
    </div>
  );
}
